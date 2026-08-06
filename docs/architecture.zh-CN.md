[English](architecture.md) | **简体中文**

# 架构

本框架在 LangGraph 之上叠加了一个工作流/智能体引擎，并通过 HTTP 以可插拔的传输协议对外暴露。本页解释各部分如何组合在一起，以及一个请求如何在其中流转。

## 核心理念

LangGraph 给你一个 `StateGraph`：节点读写一份共享状态，由边连接。本框架在其之上增加了：

1. 一个**现成节点库**（`src/goalflow/node/`），对应 Dify 这类可视化工具所暴露的构建块 —— LLM、code、HTTP、if/else、分类器、迭代、循环、tool、agent 等等。
2. 一个**转译器**（`src/goalflow/tool/dify_transformer/`），把 Dify DSL 导出文件转换成一个把这些节点接线在一起的 `BaseWorkflow` 子类，让你可视化地设计、却运行在你自己的 LangGraph 上。
3. 一个**服务 + 流式层**（`src/goalflow/workflow/services/`、`src/goalflow/workflow/chunk_processor/`、`src/goalflow/workflow/stream/`），负责驱动图、把 LangGraph 的原始流转换成语义事件，并通过 SSE 发出它们。
4. 一个**协议抽象**（`src/goalflow/workflow/services/data_adapter/`），使事件可以序列化成客户端期望的任意传输格式（默认 Dify，也内置了 OpenAI 兼容格式）。
5. 一个**智能体 SDK**（内置的 `agent_kit` 包），用于真正的智能体循环（ReAct / Deep / 自定义），并通过 `src/goalflow/node/agent_base.py` 集成进节点层。

## 组件地图

```
┌─────────────────────────────────────────────────────────────────────┐
│ HTTP layer — src/goalflow/app.py (FastAPI)                                │
│   /v1/chat-messages, /v1/chat/completions, /v1/workflows/run, ...     │
│   auth: src/goalflow/api/auth_validator.py (Bearer token → Workflow)      │
└───────────────┬───────────────────────────────────────────────────────┘
                │ initial_state (BaseState dict)
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Generate services — src/goalflow/workflow/services/                       │
│   ChatflowGenerateService / WorkflowGenerateService                   │
│   • build RunnableConfig (recursion_limit, concurrency, trace)        │
│   • yield lifecycle chunks (workflow_started, node_finished, ...)     │
│   • poll Redis stop-flag                                              │
└───────────────┬───────────────────────────────────────────────────────┘
                │ drives
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Engine — src/goalflow/workflow/base_workflow.py : BaseWorkflow[GenericState] │
│   • wraps a LangGraph StateGraph (self.graph → compiled_graph)        │
│   • execute() blocking | stream() streaming | resume() for HITL       │
│   • precomputes answer/end stream routes; binds sub-workflows         │
│   • checkpointer (MySQL) keyed by thread_id                           │
└───────────────┬───────────────────────────────────────────────────────┘
                │ raw (stream_mode, event) tuples
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Chunk processors — src/goalflow/workflow/chunk_processor/                 │
│   ChatflowStreamProcessor / WorkflowStreamProcessor                   │
│   raw stream ─► semantic events (src/goalflow/workflow/stream/types.py):  │
│   NodeRunStreamChunkEvent, NodeRunSucceededEvent,                     │
│   NodeRunInterruptEvent, NodeRunControlEvent, ProxyStreamDataChunk    │
│   • branch-aware: only streams tokens from nodes that reach END/ANSWER│
└───────────────┬───────────────────────────────────────────────────────┘
                │ semantic events
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Data adapter — src/goalflow/workflow/services/data_adapter/               │
│   AbstractDataAdapter → OpenAIDataAdapter (or your custom one)        │
│   semantic events ─► wire format (Dify default / OpenAI / custom)     │
└───────────────┬───────────────────────────────────────────────────────┘
                │ SSE  "data: {...}\n\n"
                ▼
             client

   side stores:  Redis (src/goalflow/cache/)  — hot messages, conversation vars, stop flags
                 MySQL (src/goalflow/model/)  — durable messages, HITL reviews, conversation vars
                 infra (src/goalflow/infra/)  — MySQL/Redis connection layer (engine, pools, clients)
   cross-cutting: src/goalflow/trace/ (Langfuse)   src/goalflow/monitor/ (memory)   src/goalflow/llm/ (LLM factory)
```

## 请求生命周期（流式 chatflow）

跟随 [`app.py`](../src/goalflow/app.py) 中的 `POST /v1/chat-messages`：

1. **鉴权与路由。** `validate_token_and_get_wf` 读取 `Authorization: Bearer <key>`，对 key 做 MD5 哈希，在 `apikey_workflow_def_map` 中查找，并返回一个缓存的 `BaseWorkflow` 实例。类型不匹配 → 500（`/v1/chat-messages` 要求一个 `chatflow`）。
2. **请求上下文。** 从 `X-Request-Id` 风格的请求头取得一个 `request_id`（或生成一个）并存入一个 `contextvar`。上游的 `trace_id`/`span_id` 请求头会被捕获进追踪上下文，使各服务间的 span 得以串联。
3. **初始状态。** `prepare_initial_state` 把请求体映射为一个 `BaseState` dict：`sys_query`、`sys_user_id`、`sys_app_id`、`sys_workflow_id`、`sys_conversation_id`、`sys_files`、`input_variables` 等。会分配一个全新的 `sys_workflow_run_id`（UUID）。
4. **驱动图。** `ChatflowGenerateService(workflow).generate(initial_state)` 作为一个 `StreamingResponse`（`media_type="text/event-stream"`）返回。内部它在 `workflow.stream(...)` 之上迭代流处理器，后者调用 LangGraph 的 `compiled_graph.stream(stream_mode=["updates","messages","custom"])`。
5. **语义事件。** chunk 处理器逐 token 判断发出该 token 的节点是否可证明地到达某个 `answer`/`end` 节点（分支感知路由），并发出带类型的事件。它处理 `<think>` 推理标签、token 用量提取、中断（HITL）以及控制事件。
6. **传输格式。** 事件经过当前激活的 `DataAdapter`，被序列化为 SSE 帧。
7. **持久化与停止。** 消息被写入 Redis + MySQL；每 N 个 chunk，服务会检查一次 Redis 停止标志，使 `POST /v1/chat-messages/{task_id}/stop` 能在流式过程中中止。

阻塞路径（`response_mode="blocking"`）调用 `execute()`/`.invoke()`，返回单个 JSON 响应而非一个流。

## 节点执行模型

每个节点都是一个 `BaseNode` 子类和一个 LangGraph 可调用对象（`__call__`）。子类要实现的唯一方法是 `call(state) -> NodeOutput`。围绕它，`BaseNode.__call__` 提供了统一的生命周期：

- **"node started" 日志** → **`pre_call` 扇入屏障** → **`call`** → **输出截断** → **"node finished" 日志** → **`step` 递增**。
- **路由**由返回值表达：dict 更新状态；`Command(update=..., goto=...)` 更新并跳转；`List[str]` 选择分支；`Sequence[Send]` 扇出（map-reduce，被迭代使用）。
- **扇入同步**使用 `node_level`（拓扑深度，由 `_analysis_node_level` 分配）配合一个 `step` 计数器：一个有多个前驱的节点会不断把自身重新入队，直到所有上游分支都已推进，从而在输入完整的情况下只运行一次。
- **错误策略**是每个节点独立的：`default-value`（发出一个兜底值并继续）或 `fail-branch`（沿 `fail_branch_node_ids` 路由）。

完整细节和每个节点的配置在 [nodes.md](nodes.md) 中；状态 schema 和 reducer 在 [storage-and-config.md](storage-and-config.md#state) 中。

## 图 vs. 循环 —— 以及如何结合它们

- **工作流图**擅长显式、可审计的控制流，但对开放式推理则略显笨拙。
- **智能体循环**（ReAct/Deep）擅长开放式的工具使用，但更难约束、也更难逐步观测。

本框架让你可以把两者结合：

- 一个 **`AgentNode` / `AgentBaseNode`** 把一个智能体循环嵌入到一个图节点中。`AgentBaseNode`（参见 [`agent_base.py`](../src/goalflow/node/agent_base.py)）多重继承了 `BaseNode` 和内置 `agent_kit` 的 `Agent`，因此一个智能体循环就只是你 LangGraph 中的又一个节点，通过同一条流水线流式输出 token。
- 一个工作流可以被绑定为一个**子工作流**，并从另一个工作流内部被调用（通过 `bind_subworkflows()` 以及状态中的子工作流桥接字段），这样智能体可以把结构化流程当作工具来调用，反之亦然。

智能体这一侧参见 [agent-kit.md](agent-kit.md)。

## 接下来去哪

| To understand… | Read |
|----------------|------|
| 每种节点类型 | [nodes.md](nodes.md) |
| 把 Dify DSL 转成工作流 | [dify-transformer.md](dify-transformer.md) |
| 替换传输协议 | [protocols-and-adapters.md](protocols-and-adapters.md) |
| Token 流式与 HITL 内部机制 | [streaming-and-hitl.md](streaming-and-hitl.md) |
| 状态字段、Redis/MySQL、配置 | [storage-and-config.md](storage-and-config.md) |
| 智能体 SDK | [agent-kit.md](agent-kit.md) |
