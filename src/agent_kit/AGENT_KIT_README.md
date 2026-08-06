# agent_kit

跨形态 Agent 工具箱 + Harness 治理底座。让任何 LangGraph 项目用几十行代码就拥有：

- **一个 Agent 抽象**：4 个钩子（3 必填 + 1 可选），不再继承 12 钩子的庞大基类
- **3 种底层 graph 形态**：ReAct（`create_agent`）/ Deep（`create_deep_agent`）/ Custom（手拼 `StateGraph`），通过 `GraphBuilder` 策略对象切换
- **9 个可插拔中间件**：短路 / 跳过 LLM / 兜底 / 敏感词 / 历史注入 / 动态 prompt / skills / metrics / streaming / Langfuse —— 全部以 `middleware=[...]` 注入，而非钩子
- **可注入的治理容器 `Harness`**：Model Router / Prompt Registry / Observability / Profiles，显式注入、便于单测隔离
- **渐进披露式 Skill 系统**：遵循 Anthropic `SKILL.md` 规范，prompt-only / executable / hybrid 三种模式

> v2.0.0 引入了全新的 `Agent` + `Harness` + `GraphBuilder` API（ADR-003）。
> 旧的 `AgentRuntime` / `CreateAgentRuntime` / `DeepAgentRuntime` / `StateGraphRuntime` + `HARNESS_*`
> 全局单例 **继续可用**（override 废弃钩子会发 `DeprecationWarning`），两套 API 并存。
> 新项目请用下文的 `Agent` API。

## 安装

```bash
pip install -e .                 # 本地开发（仓库根目录即包根目录）
pip install -e ".[dev]"          # 含测试依赖
pip install -e ".[langfuse]"     # 含 Langfuse trace 支持
pip install -e ".[skills]"       # 含 Skill 系统（PyYAML）
```

要求 Python ≥ 3.10。核心依赖：`pydantic` / `langchain` / `langchain-core` / `langgraph` / `deepagents` / `jinja2`。

## 设计：Agent + GraphBuilder + Middleware + Harness

```
                ┌──────────────────────────────────────────────┐
   你的子类  →  │  Agent[OutputT]                                │
                │   • output_schema()      声明结构化输出         │
                │   • build_prompt(state)  构造 system prompt     │
                │   • serialize_output()   输出 → LangGraph Command│
                │   • format_user_input()  可选：自定义 user 消息  │
                └──────────────────────────────────────────────┘
                  │ graph_builder      │ middleware=[...]   │ harness
                  ▼                    ▼                    ▼
        ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
        │  GraphBuilder     │  │  Middleware       │  │  Harness          │
        │  ─ ReactGraph     │  │  约束类 4         │  │  ─ settings       │
        │  ─ DeepGraph      │  │  增强类 5         │  │  ─ router         │
        │  ─ CustomGraph    │  │  + dynamic prompt │  │  ─ prompts        │
        │  （自定义策略）    │  │   工厂            │  │  ─ tracer         │
        └──────────────────┘  └──────────────────┘  │  ─ profiles       │
                                                      └──────────────────┘
```

- **Agent** 只关心「输入 → prompt → 结构化输出 → Command」四件事。
- **GraphBuilder** 决定底层用哪种 LangGraph 形态构建（默认 `ReactGraphBuilder`）。
- **Middleware** 承接所有横切关注点；执行顺序即列表顺序。
- **Harness** 是治理依赖的实例化容器，通过 `harness=` 注入；不传则 `model=` 必填。

## 最小示例（不接 Harness，直接传 model）

```python
from agent_kit import Agent
from langgraph.types import Command
from pydantic import BaseModel


class ClassifyOutput(BaseModel):
    reply: str = ""
    label: str = ""


class CategoryClassifier(Agent[ClassifyOutput]):
    name = "category_classify"               # 同时充当 router task_type / metric 前缀

    def output_schema(self):
        return ClassifyOutput

    def build_prompt(self, state):
        return "你是一个企业服务类目分类器。返回 reply 和 label 两个字段。"

    def serialize_output(self, state, output):
        if isinstance(output, ClassifyOutput):
            return Command(update={"reply": output.reply, "label": output.label})
        return Command(update={"reply": str(output)})


# model 可以是 BaseChatModel 实例、模型名字符串、或 None（None 时从 harness.router 取）
agent = CategoryClassifier(model="qwen-plus")
cmd = agent.run({}, "帮我找一家做税务筹划的公司")
print(cmd.update["label"])
```

`Agent` 的三态 model 解析：

| `model` 传入 | 行为 |
|--------------|------|
| `BaseChatModel` 实例 | 直接使用 |
| `str`（如 `"qwen-plus"`） | `langchain.chat_models.init_chat_model(...)` 实例化 |
| `None` | 从 `harness.router.get(self.name)` 取（需传 `harness=`） |

## 选择底层 graph 形态（GraphBuilder）

默认是 `ReactGraphBuilder`。需要其它形态时构造时注入 `graph_builder=`：

| 场景 | GraphBuilder | 底层 |
|------|--------------|------|
| 分类 / 提取 / 改写 / 简单 QA（最常用 tool-calling） | `ReactGraphBuilder` | `langchain.agents.create_agent` |
| 多步骤需求收集、planning / todos / subagents / HITL 中断 | `DeepGraphBuilder` | `deepagents.create_deep_agent` |
| 完全自定义状态机（议价 Tit-for-Tat、复核流水线） | `CustomGraphBuilder` | 你提供的 `builder_fn` |

```python
from agent_kit import Agent, DeepGraphBuilder, CustomGraphBuilder

# Deep：带 subagents / memory / HITL 中断
agent = MyAgent(
    model=llm,
    graph_builder=DeepGraphBuilder(
        subagents=[...],
        memory=["AGENTS.md"],
        interrupt_on={"dangerous_tool": True},
    ),
)

# Custom：传一个 (model, tools, middleware, output_schema, **extra) → CompiledGraph 的 callable
def my_builder(*, model, tools, middleware, output_schema=None, **kw):
    from langgraph.graph import StateGraph
    from langgraph.checkpoint.memory import InMemorySaver
    g = StateGraph(MyState)
    g.add_node("decide", decide_node)
    g.set_entry_point("decide")
    return g.compile(checkpointer=InMemorySaver())

agent = MyAgent(model=llm, graph_builder=CustomGraphBuilder(my_builder))
```

## 9 个中间件（横切关注点）

通过 `middleware=[...]` 注入，按列表顺序执行。分两类：

**约束类**（控制 agent loop 走向）

| 中间件 | 作用 | 替代旧钩子 |
|--------|------|-----------|
| `EntryGuardMiddleware` | 入口短路预检 | `before_call` |
| `ModelSkipMiddleware` | 跳过 LLM 调用直接回 | `should_run_agent` |
| `FallbackReplyMiddleware` | 异常兜底文案 | `on_failure` |
| `SensitiveCheckMiddleware` | 敏感词校验，违规 `jump_to=end` | — |

**增强类**（修改 / 扩展 model 调用）

| 中间件 | 作用 |
|--------|------|
| `ConversationHistoryMiddleware` | 注入对话历史（配 `ConversationStore`），可选回写本轮 |
| `SkillAugmentationMiddleware` | 匹配并把 skill 详情拼进 prompt / materialize 成 tool |
| `MetricsMiddleware` | 自动埋点 model 调用延迟 / 失败 |
| `StreamingBridgeMiddleware` | 把 model token 输出推到 stream callback |
| `LangfuseTracingMiddleware` | 包围 agent 生命周期开 / 关 Langfuse span |

外加工厂函数 `make_dynamic_prompt_middleware()`：从 Langfuse / 本地 / fallback 三层 source 构造动态 prompt 中间件。

## 治理容器 Harness

`Harness` 把原先 5 个进程级全局单例收敛为一个可注入的实例容器：

```python
from agent_kit import Harness, default_harness

harness = default_harness()      # 进程级默认；其属性就是旧 HARNESS_* 单例本身（共享状态）
# 或单测隔离：
harness = Harness()              # 全新独立的 router / prompts / tracer / profiles
```

| 属性 | 类型 | 职责 |
|------|------|------|
| `harness.settings` | `HarnessSettings` | 跨业务通用默认（LLM 默认值 / Obs / Fallback 策略）|
| `harness.router` | `ModelRouter` | `task_type → LLM` 路由，启动时 `register_llm_factory(...)` + `configure(...)` |
| `harness.prompts` | `PromptRegistry` | 三层 prompt 加载（Langfuse → 本地 j2 → Python fallback）|
| `harness.tracer` | `Observability` | 统一 metric / trace 接入点 |
| `harness.profiles` | `ProfileRegistry` | 一次 `register()` 收敛「配 LLM + 注册 Prompts + skills_dir + 阈值」 |

应用启动时接线一次：

```python
from agent_kit import default_harness
from your_app.llm import LLM

h = default_harness()
h.router.register_llm_factory(LLM.create)         # 注入工厂，agent_kit 不绑定具体 LLM
h.router.configure("category_classify", temperature=0.1, model="qwen-plus")
h.tracer.enable_langfuse()                         # 可选
```

## 生产级示例（Agent + Harness + 全套中间件）

```python
from agent_kit import (
    Agent, default_harness,
    EntryGuardMiddleware, SensitiveCheckMiddleware, ModelSkipMiddleware,
    FallbackReplyMiddleware, ConversationHistoryMiddleware,
    MetricsMiddleware, StreamingBridgeMiddleware, LangfuseTracingMiddleware,
    make_dynamic_prompt_middleware,
)
from langgraph.types import Command
from pydantic import BaseModel


class ChatOutput(BaseModel):
    reply: str = ""


class ProductionAgent(Agent[ChatOutput]):
    name = "production_chat"

    def __init__(self, **kw):
        harness = default_harness()
        super().__init__(
            harness=harness,
            middleware=[
                EntryGuardMiddleware(lambda state, runtime: None),
                SensitiveCheckMiddleware(),
                ModelSkipMiddleware(lambda state, rt: ("low_signal", "好的") if is_ack(state) else None),
                FallbackReplyMiddleware(fallback_reply="抱歉服务暂时不可用，请稍后重试。"),
                ConversationHistoryMiddleware(save_turn=True),
                make_dynamic_prompt_middleware(),
                MetricsMiddleware(harness, prefix="production_chat"),
                StreamingBridgeMiddleware(),
                LangfuseTracingMiddleware(harness, span_prefix="production_chat"),
            ],
            **kw,
        )

    def output_schema(self):
        return ChatOutput

    def build_prompt(self, state):
        return "你是一个专业的客户服务助手。回答要简洁友好。"

    def serialize_output(self, state, output):
        text = output.reply if isinstance(output, ChatOutput) else str(output)
        return Command(update={"reply": text})
```

运行时通过 `config` 传入会话 id / stream callback：

```python
agent.run({}, "你好", config={
    "configurable": {
        "sys_conversation_id": "conv-1",
        "stream_callback": lambda t: print(t, end="", flush=True),
    }
})
```

## Skill 系统

遵循 Anthropic `SKILL.md` 规范的渐进披露式 skill：扫盘解析 frontmatter → LLM 匹配 → 按需加载 body。三种模式：

- **prompt-only**：把 skill body 拼进 system prompt
- **executable**：`module:func` materialize 成 LangChain Tool 注入 graph
- **hybrid**：两者兼具

业务侧通常通过 `SkillAugmentationMiddleware` 或 `HarnessProfile(skills_dir=...)` 启用。详见 `agent_kit/skills/` 与 `examples/harness_skills_agent.py`。

## 完整 examples

见 `examples/`：

| 文件 | 内容 | API |
|------|------|-----|
| `minimal_agent.py` | 最小骨架，直接传 model | 新 |
| `conversation_agent.py` | 历史注入 + 敏感词中间件 | 新 |
| `full_governance.py` | Harness + 全套中间件治理 | 新 |
| `harness_skills_agent.py` | Harness × Skills 四件套联动 | 旧（兼容演示）|
| `minimal_create_agent.py` / `minimal_deep_agent.py` / `minimal_state_graph.py` / `harness_e2e.py` | 旧 Runtime API | 旧 |

## 测试

```bash
pip install -e ".[dev]"
pytest tests/ -q                 # 30 个测试模块，300+ 用例
```

## 旧 API（已废弃，仍可用）

`AgentRuntime` 及其三个子类 `DeepAgentRuntime` / `CreateAgentRuntime` / `StateGraphRuntime`、
`HarnessBacked` mixin、`HARNESS_SETTINGS` / `HARNESS_ROUTER` / `HARNESS_PROMPTS` / `HARNESS_OBS` / `HARNESS_PROFILES`
全局单例继续从 `agent_kit` 导出且行为不变。override 已被中间件覆盖的钩子（如 `before_call` /
`should_run_agent` / `on_failure`）会触发 `DeprecationWarning`。新代码请迁移到 `Agent` + `Harness` + `middleware`。

## 版本历史

见 [CHANGELOG.md](CHANGELOG.md)。
