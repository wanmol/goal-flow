[English](agent-kit.md) | **简体中文**

# Agent Kit（`agent_kit`）

`agent_kit` 是一个与框架无关的 SDK，用于在 LangGraph 之上构建 **智能体循环（agent loop）**。它以包的形式内置（vendor）在本仓库的 `src/agent_kit/` 中，提供了智能体运行时、一条中间件流水线、模型路由/故障转移、一套可执行技能系统，以及可观测性——全部隐藏在一个小巧的 `Agent` 基类之后。

> 该 SDK 被直接内置到本仓库的 `src/agent_kit/` 中。将其作为独立依赖发布（例如发布到 PyPI）在路线图之中——参见 [design-notes.md](design-notes.md#agent-kit-integration)。

## 为什么要单独做一个 kit

纯粹的工作流图擅长处理显式的控制流；纯粹的智能体循环擅长开放式的工具使用。二者单独都无法覆盖全部场景，因此该 kit 被设计为可以作为一个节点 **嵌入** 到工作流中（通过 `src/goalflow/node/agent_base.py`），让你能够混用 `graph + loop`。参见 [architecture.md](architecture.md#graph-vs-loop--and-combining-them)。

## `Agent` 类

`Agent[OutputT]`（`src/agent_kit/agent.py`）是公开的入口点。你继承它并实现一小组钩子：

| 钩子 | 是否必需 | 用途 |
|------|----------|---------|
| `output_schema()` | 是 | 结构化输出类型（Pydantic） |
| `build_prompt(state)` | 是 | 本轮的系统提示词 |
| `format_user_input()` | 否 | 塑造用户消息 |
| `format_output()` | 否 | 对最终答案进行后处理 |

构造时接受 `model`、`tools`、`subagents`、`middleware=[...]`、`graph_builder`、`harness` 和 `cache_graph`。

模型解析（`_resolve_model`）是三态的：显式的 `BaseChatModel` > 模型字符串（`init_chat_model`）> harness 路由器（`harness.router.get(self.name)`）。

`run(state, user_query, config)` 编译图、构建提示词、驱动 `graph.stream(stream_mode="messages")`，将每个 `AIMessageChunk` 推送到 `config.configurable["stream_callback"]`，并返回 `structured_response`（或经 `format_output` 处理后的最后一段 AI 文本）。

## 图构建器（智能体拓扑）

`GraphBuilder` 协议（`src/agent_kit/graphs/base.py`）只有一个方法：`build(*, model, tools, middleware, output_schema, **extra)`。共有三种实现：

| 构建器 | 封装 | 适用于 |
|---------|-------|---------|
| `ReactGraphBuilder`（`react.py`） | `langchain.agents.create_agent` | 标准的 ReAct 工具使用循环（默认） |
| `DeepGraphBuilder`（`deep.py`） | `deepagents.create_deep_agent` | 子智能体、记忆（AGENTS.md）、HITL `interrupt_on` |
| `CustomGraphBuilder`（`custom.py`） | 你自己的 `builder_fn` | 手工构建的 `StateGraph` |

当存在 `subagents` 时，`Agent` 会自动选择 `DeepGraphBuilder`（并注入 `SubAgentInitializeMiddleware`），否则选择 `ReactGraphBuilder`。

## 中间件流水线

中间件（`src/agent_kit/middleware/`）按列表顺序运行，取代了以往按运行时划分的钩子。它们分为两组：

**约束 / 控制**
- `EntryGuardMiddleware` —— 控制智能体是否运行。
- `ModelSkipMiddleware` —— 在特定条件下跳过模型调用。
- `ModelFailoverMiddleware` —— 失败时回退到另一个模型。
- `FallbackReplyMiddleware` —— 全部失败时给出预设的兜底回复。
- `SensitiveCheckMiddleware` —— 内容安全。

**增强**
- `ConversationHistoryMiddleware` —— 注入先前的对话轮次。
- `SkillAugmentationMiddleware` —— 匹配并注入技能（见下文）。
- `MetricsMiddleware` —— 上报指标。
- `StreamingBridgeMiddleware` —— 将 token 桥接到工作流的流式输出。
- `LangfuseTracingMiddleware` —— 追踪 span。

此外还有 `SubAgentInitializeMiddleware` 以及工厂函数 `make_dynamic_prompt_middleware`。

## Harness（治理容器）

`Harness` 数据类（`src/agent_kit/harness/`）是一个可注入的横切服务容器：

- `HarnessSettings`（`settings.py`）—— `LLMDefaults`（提供方 `qwen`、模型 `qwen-plus`、温度、超时、重试）、可观测性、兜底回复设置。
- `ModelRouter`（`model_router.py`）—— 将 `task_type → LLM` 映射。`register_llm_factory()` 注入 LLM 工厂（使 kit 保持与具体 LLM 无关），`configure(task_type, ...)` 设置每种任务的配置，`get()` 带缓存地解析，`register_fallback_factory()` 提供故障转移。
- `PromptRegistry` —— 具名提示词。
- `HarnessProfile` / `ProfileRegistry`（`profiles.py`）—— 一次调用即可注册一个 LLM + 子 LLM + 提示词 + `skills_dir` + 技能匹配参数，并将它们分发到路由器和提示词注册表。
- `tracer` —— 可观测性钩子。

`default_harness()` 绑定到进程级的 `HARNESS_*` 单例（共享状态）；而一个裸的 `Harness()` 是隔离的（便于测试）。

## 技能（可执行）

该 kit 的技能系统（`src/agent_kit/skills/`）与主项目的 [技能引擎](skills.md) 相仿，但额外支持三种模式：

- **prompt-only（仅提示词）** —— 注入指令（与主项目引擎相同），
- **executable（可执行）** —— 一个 `module:func` 引用，被物化为智能体可调用的 LangChain `Tool`，
- **hybrid（混合）** —— 二者兼具。

通过 `SkillAugmentationMiddleware` 或 `HarnessProfile(skills_dir=...)` 启用。

## 与工作流层的集成

`src/goalflow/node/agent_base.py::AgentBaseNode(BaseNode, Agent[OutputT])`（ADR-004）多重继承了工作流的 `BaseNode` 和 kit 的 `Agent`。它新增了一个钩子：

```python
def build_command(self, state, output) -> Command:
    """Translate the agent's output into a LangGraph Command (state update + routing)."""
```

`BaseNode.call(state)` 会设置一个 `stream_callback`（通过 `RunnableConfig.configurable`，并由一个 `ContextVar` 守护以实现按请求隔离），调用 `Agent.run`，然后执行 `build_command`。它使用 `default_harness()` 来共享 `HARNESS_*` 单例，并由 `src/goalflow/node/_harness_bootstrap.py::ensure_harness_wired()`（幂等）将本仓库的 `LLM` 工厂、指标和 Langfuse 接入这些单例。

`AgentBaseNode` 取代了三个已弃用的基类（`DeepAgentBaseNode`、`CreateAgentBaseNode`、`StateGraphBaseNode`）。要构建一个新的智能体节点，继承 `AgentBaseNode` 并实现 `output_schema`、`build_prompt` 和 `build_command`。

## 学习路径

- 内置包自带的 `src/agent_kit/README.md` 提供了聚焦于 SDK 的完整讲解。
- 可运行的示例位于 `src/agent_kit/examples/`（`minimal_agent.py`、`conversation_agent.py`、`full_governance.py`、`harness_e2e.py`、`minimal_deep_agent.py` 等）。
- `src/agent_kit/tests/` 中的测试同时充当每个中间件和构建器的行为规范。
