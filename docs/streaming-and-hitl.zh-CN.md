[English](streaming-and-hitl.md) | **简体中文**

# 流式与人在环

本页说明 token 如何从引擎流式输出，以及工作流如何在运行途中暂停以等待人工输入。

## 三层流式管线

```
BaseWorkflow.stream()            LangGraph raw stream: (mode, event) tuples
        │                        modes: "updates" | "messages" | "custom"
        ▼
StreamProcessor                  raw tuples ─► semantic events
        │                        (workflow/stream/types.py)
        ▼
GenerateService.generate()       semantic events ─► lifecycle chunks (+ Redis stop check)
        │
        ▼
DataAdapter                      ─► SSE frames to the client
```

### 第 1 层 —— 引擎（`BaseWorkflow.stream`）

`BaseWorkflow.stream(initial_state, config, stream_mode)` 调用 LangGraph 的 `compiled_graph.stream(...)`，并产出原始的 `(stream_mode, event_data)` 元组。它运行时携带一个 `RunnableConfig`，其中包含 `recursion_limit=500`、`max_concurrency=6`、追踪元数据以及一个 `thread_id`（检查点键）。有两种 LangGraph 流式模式承载着关键数据：

- **`messages`** —— 来自 LLM 节点的逐 token 输出。
- **`updates`** —— 节点完成时的快照。
- **`custom`** —— 中断、控制事件和透传数据。

### 第 2 层 —— 数据块处理器（`workflow/chunk_processor/`）

处理器将原始元组转换为 `workflow/stream/types.py` 中带类型的语义事件：
`NodeRunStreamChunkEvent`、`NodeRunSucceededEvent`、`NodeRunInterruptEvent`、`NodeRunControlEvent`、`ProxyStreamDataChunk`。

两个处理器，分别对应一种工作流类型：

- **`WorkflowStreamProcessor`** —— 将流式 token 导向 `end` 节点。
- **`ChatflowStreamProcessor`** —— 将流式 token 导向 `answer` 节点；同时通过 `custom` 模式处理中断、控制事件和透传数据。

**分支感知的流式**是其中巧妙的部分。收到 `messages` 事件时，处理器查看 `metadata["langgraph_node"]` 来确定是哪个节点发出了该 token，然后在已经走过的分支基础上判断该节点是否*可证明地能够到达* `answer`/`end` 节点。只有满足条件时才转发这些 token。`_remove_dependencies` 会剪掉分支节点（`if-else`、`question-classifier`、`fail-branch`）的边，因此来自*未被选中*分支的 token 永远不会流式传给用户。收到 `updates` 时，它发出 `NodeRunSucceededEvent`，推进路由位置，并为已完成的 `end`/`answer` 依赖冲刷出任何静态模板文本。

它还处理：
- **推理标签** —— `<think>` / `</think>` 内容会被分离出来（键为 `THINK_START_TAG`、`THINK_END_TAG`、`THINKING_CONTENT_KEY` = `reasoning_content`）。
- **Token 用量** —— 在 `finish_reason == "stop"` 时提取。

### 第 3 层 —— 生成服务（`workflow/services/`）

`WorkflowGenerateService.generate(initial_state)` / `ChatflowGenerateService.generate(initial_state)` 是生成器，它们：

1. 设置 `request_id` contextvar 并分配 `sys_workflow_run_id`，
2. 产出一个 `workflow_started` 数据块，
3. 构建 `RunnableConfig`，
4. 在 `workflow.stream(...)` 之上迭代流处理器，将语义事件映射为客户端数据块：
   - `NodeRunSucceededEvent` → `node_finished`（拆包 `output_variables`），
   - `NodeRunStreamChunkEvent` → `text_chunk`，
5. 每隔 `STREAM_OUTPUT_STOP_CHECK_INTERVAL` 个数据块，检查一次 Redis 停止标志，以便中止本次运行。

最后，这些数据块经过当前激活的 [DataAdapter](protocols-and-adapters.md)，并作为 SSE 帧写出（`data: {...}\n\n`）。

### 停止一次运行

`POST /v1/chat-messages/{task_id}/stop` 会设置一个 Redis 标志（`generate_task_stopped:<id>`）。生成服务轮询该标志并终止流。这就是为什么长时间的生成可以从客户端取消。

## 人在环（HITL）

HITL 让工作流能够**暂停、询问人工、然后恢复**——用于审批、纠正或澄清。

### 暂停如何工作

- 某个节点抛出一个 LangGraph **中断**。由于图是带**检查点器**（MySQL，以 `thread_id` 为键）编译的，其完整状态会在中断点被持久化。
- 数据块处理器将其暴露为一个 `NodeRunInterruptEvent`，服务再将其作为中断数据块流式传给客户端（客户端由此得知需要什么输入）。

### 恢复如何工作

- 客户端将人工决策提交到 HITL API（[`api/hitl_api.py`](../api/hitl_api.py)）。
- `BaseWorkflow.resume(resume_data, config)` 针对同一个 `thread_id` 发出一个 LangGraph `Command(resume=...)`，因此执行会从暂停处精确地继续——不会重跑先前的节点。
- 决策通过 HITL 服务（`workflow/services/workflow_hitl_service.py`）记录并持久化（`db/hitl_review.py`）。决策类型包括 `approve` / `reject` / `modify`（见 `constants.py`）。

### 控制事件

`NodeRunControlEvent`（来自 `custom` 流式模式，事件名为 `WF_NODE_CONTROL_EVENT_NAME`）让工作流能够告诉前端去做一些事情，比如**清除当前输出并重新生成**——当一次 HITL 纠正使已经流式输出的内容失效时，这很有用。

## 检查点

检查点器是停止/恢复和 HITL 二者的支柱。它由 `workflow/utils/checkpointer_manager.py`（配合 `connection_wrapper.py` 处理 MySQL 连接）管理，使用 `langgraph-checkpoint-mysql`。每次运行都会获得一个 `thread_id`；状态在每个超级步（super-step）被快照化，因此一次运行可以被暂停、检视并持久地恢复。

持久化布局见 [storage-and-config.md](storage-and-config.md)，HITL 端点见 [api-reference.md](api-reference.md)。
