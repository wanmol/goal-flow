[English](nodes.md) | **简体中文**

# 节点参考

节点是工作流的构建块。每个节点都是 `BaseNode`（`src/goalflow/node/base.py`）的子类，同时也是一个 LangGraph 可调用对象。本页先介绍基础抽象，然后逐一讲解每个内置节点。

节点类型注册表是 [`constants.py`](../src/goalflow/constants.py) 中的 `WfNodeType`；每种类型与一个 Dify 节点类型字符串一一对应，[转译器](dify-transformer.md)正是借此得知该发射哪个节点类。

## 基础节点

`BaseNode(ABC, Generic[GenericState])` —— 所有节点的根。

### 你需要实现什么

恰好一个方法：

```python
def call(self, state: GenericState) -> NodeOutput: ...
```

`NodeOutput` 是一个联合类型，同时编码了**状态更新**和**路由**：

| Return type | Meaning |
|-------------|---------|
| `dict` / `TypedDict` | 将这些键合并进状态，继续前往 `next_node_ids` |
| `Command(update=..., goto=...)` | 更新状态并跳转到指定节点 |
| `List[str]` | 分支路由 —— 选择这些出向 handle |
| `Sequence[Send]` | 扇出（map-reduce），每个 `Send` 对应一条并行分支 |
| `None` | 无更新 |

### 生命周期（`__call__`）

每个节点都会经过同一个包装器，因此你可以免费获得一致的计时、日志、扇入（fan-in）和错误处理：

1. 记录 `start_time`（`time.perf_counter()`），并打印 **"node started"** 日志，附带 `step`、`node_level`、`wf_name`、`node_type`、`node_id`、`node_title`（当 `isInIteration` 时另附 `iteration_round`）。
2. `pre_call(state)` —— **扇入屏障（fan-in barrier）**。如果节点有多个 `pre_node_ids` 且尚未到达其拓扑深度（`node_level >= step + 1`），它会返回 `Command(update={"step": step+1}, goto=[self.id])` 将自身重新入队，以便只有当所有上游分支都到达后才真正运行。（`END`/`ANSWER` 会跳过这一步。）
3. `self.call(state)` —— **你的逻辑**。
4. 从返回的 `Command` 中取出 `goto` → `next_node_ids`、`update` → `output`，将 `output` 经 `truncate_output_value` 处理，计算 `cost_time`，并打印 **"node finished"** 日志（当 `isInIteration` 时另附 `iteration_item`）。
5. 将 `step` 递增写入 `value.update` 并返回 —— **但** `END`/`ANSWER` 除外，它们返回原始输出且不递增 `step`。
6. 出现异常时 → 直接重新抛出（由外层运行器捕获，并向前端发送 error 事件）。

### 关键属性

`id`、`title`、`desc`、`type`、`variables`、`error_strategy`、`default_value`、`pre_node_ids`、`next_node_ids`、`fail_branch_node_ids`、`parent_node_id`、`node_level`、`wf_name`，外加循环/迭代标志 `isInIteration`、`isInLoop`、`iteration_id`、`loop_id`。

### 路由与错误

- **边（Edges）**由工作流声明为 `GraphEdge`；转译器会把它们解析进每个节点的 `next_node_ids`、`fail_branch_node_ids` 和 `source_handle_target_map`（用于分支节点）。
- **`node_level`** 是由 `BaseWorkflow._analysis_node_level` 分配的拓扑深度，与 `step` 一起用于扇入。
- **错误策略**（`error_strategy`，来自 Dify 配置）：
  - `default-value` —— 失败时发出 `default_value` 并正常继续。
  - `fail-branch` —— 失败时发出 `source_handle="fail-branch"` 并路由到 `fail_branch_node_ids`。

## 节点目录

每个节点对应一个 `WfNodeType` 及其 Dify 等价物。

### 流程控制

| Node | Type | Purpose |
|------|------|---------|
| **StartNode** | `start` | 入口。校验声明的输入（必填 / 类型 / 选择项 / 默认值），初始化 `input_variables`，从数据库加载 `conversation_variables`，暴露 `sys.query`。 |
| **EndNode** | `end` | 终点。解析输出选择器并返回 `{"outputs": ...}`。不递增 `step`。 |
| **AnswerNode** | `answer` | Chatflow 终点。用变量分块插值一段文本模板并将其流式输出（通过 `AnswerEndStreamOutRouter`）。 |
| **IfElseNode** | `if-else` | 用 `ConditionProcessor` 按顺序求值各 case；按 `selected_case_id` 路由（兜底为 `"false"`）。 |
| **ClassifierNode** | `question-classifier` | 由 LLM 选择一个类别；通过 `source_handle_target_map[category_id]` 路由。 |

### 数据与转换

| Node | Type | Purpose |
|------|------|---------|
| **CodeNode** | `code` | 运行沙箱化的 Python（使用受限 `__builtins__` 的 `exec`）。要求有一个返回 dict 的 `main()`；输出会被过滤到声明的 `outputs`。 |
| **TemplateTransformNode** | `template-transform` | 将一个 Jinja2 模板渲染到 `output`。 |
| **AggregatorNode** | `variable-aggregator` | 返回 `variable_selectors` 中第一个非空值；通过 `advanced_settings` 支持分组模式。 |
| **AssignerNode** | `assigner` | 变量操作（覆写 / 追加 / 扩展 / 加 / 减 / 清空 / 设置等）。将会话变量持久化到数据库。 |
| **DocExtractorNode** | `document-extractor` | 按 MIME 类型从上传文件中提取文本（pdf、docx、xlsx、ppt、epub、eml、csv 等）。 |

### LLM 与智能体

| Node | Type | Purpose |
|------|------|---------|
| **LLMNode** | `llm` | 核心 LLM 调用。由 `model` / `prompt_template` / `memory` / `context` / `vision` 构建 prompt，流式输出，支持 JSON 提取和错误策略。 |
| **AgentNode** | `agent` | 手动 ReAct 循环：将工具绑定到 Azure/通义 LLM，运行 `handle_tool_calls`，再做第二次调用得到最终答案，最多重试 3 次。 |
| **AgentBaseNode** | (base) | 基于内置 `agent_kit` 的 `Agent` + 图构建器打造的新一代智能体基类（ADR-004）。子类实现 `output_schema`、`build_prompt`、`build_command`。参见 [agent-kit.md](agent-kit.md)。 |

### 外部与检索

| Node | Type | Purpose |
|------|------|---------|
| **HttpRequestNode** | `http-request` | 模板化的 HTTP 请求（url/headers/params/body），支持 SSE、重试/超时、fail-branch/default-value。 |
| **ToolNode** | `tool` | 按 `tool_provider_config` 执行一个绑定的外部工具函数，带指数退避重试（不可重试：`ValueError`、`TypeError` 等）。 |
| **KnowledgeRetrievalNode** | `knowledge-retrieval` | 已弃用的桩实现，返回空结果（为保持图兼容性而保留）。 |

### 迭代与循环

| Node | Type | Purpose |
|------|------|---------|
| **IterationNode**（+ `IterationStartNode`） | `iteration` | 构建一个内部 `StateGraph`，用 `Send` 在 `iterator_selector` 上扇出（支持 `parallel_nums` / `is_parallel`），并收集 `output_selector`。 |
| **LoopNode**（+ `LoopStartNode`、`LoopEndNode`） | `loop` | 将一个子图运行至多 `loop_count` 次（硬上限 10），每轮重置 `step=0` 并检查 `break_conditions`。`LoopEndNode` 可发出提前退出信号。 |

### 自定义节点（`src/goalflow/node/custom/`）

这些是领域特定的示例，展示如何添加你自己的节点类型：

| Node | Type | Purpose |
|------|------|---------|
| **NaturalLanguageQueryNode** | `nl_db_query` | 一个完整的 text-to-SQL ReAct 子图：列出表 → 获取 schema → 生成 SQL → 检查 → 运行。 |
| **SensitiveWordCheckNode** | `sensitive_word_check` | 运行 `text_to_img_check`；输出 `passed` / `status`。 |

## 添加新的节点类型

1. 继承 `BaseNode[YourState]` 并实现 `call(self, state)`。
2. 如果它对应一个新的 Dify 类型，在 `src/goalflow/constants.py` 中添加一个 `WfNodeType` 条目。
3. 从 `src/goalflow/node/__init__.py` 导出它。
4. 在 `src/goalflow/visitor/node_visitor.py` 中添加一个 `visit_<type>` 处理器，以便转译器能发射它（如果你想要 DSL 支持）。

对于智能体风格的节点，优先继承 `AgentBaseNode`（参见 [agent-kit.md](agent-kit.md)），而不是手动的 `AgentNode` 循环。

## 节点如何变成一个运行中的图

[转译器](dify-transformer.md)会生成一个 `BaseWorkflow` 子类，其 `_setup_nodes` 构造这些节点对象，`_setup_edges` 构建 `GraphEdge`。`BaseWorkflow.__init__` 会执行这两者，把节点加入一个 LangGraph `StateGraph`，通过 `_analysis_node_level` 分配节点层级，并用 MySQL checkpointer 编译它。参见 [architecture.md](architecture.md#the-node-execution-model)。
