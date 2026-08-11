[English](tutorials.md) | **简体中文**

# 端到端教程

针对多数人上手 goalflow 后最想做的三件事,提供三份实操演练:

1. [转译一个小型 Dify 流程并调用它](#教程-1--转译一个小型-dify-流程并调用它) —— 完整的"可视化设计 → 运行中的服务"闭环。
2. [用 `AgentBaseNode` 构建一个 agent 节点](#教程-2--用-agentbasenode-构建一个-agent-节点) —— 把一个 `agent_kit` 循环作为工作流节点嵌入。
3. [实现一个自定义 `DataAdapter`](#教程-3--实现一个自定义-dataadapter) —— 新增一种客户端通信协议。

这些教程假设你已完成 [快速开始](getting-started.zh-CN.md)(克隆、`pip install -e .`、可用的 `.env`、Redis 与 MySQL 可达)。

> [!NOTE]
> 教程 2 与教程 3 涉及的代码**已定义,但尚未接入默认请求链路**(见各节的坦诚说明)。它们的写法保证你产出的代码对照当前 API 是正确的,并明确标出哪些地方是在**扩展框架**、而非沿着现成路径走。

---

## 教程 1 — 转译一个小型 Dify 流程并调用它

**目标:** 在 Dify 里设计一个最小 chatflow,把导出的 DSL 转译成一个可运行的工作流类,注册它,再通过 HTTP 调用。

### 1.1 在 Dify 里设计并导出

在 Dify Studio 里搭一个最小可用的 chatflow:

```
Start → LLM → Answer
```

- **Start** —— 无需配置。
- **LLM** —— 选一个模型,提示词写成类似 `简洁地回答用户:{{#sys.query#}}`。
- **Answer** —— 输出 LLM 节点的文本。

导出(`... → 导出 DSL`)为 `my_flow.yml`。

### 1.2 把 DSL 转译成工作流类

在项目根目录以模块方式运行转译器:

```bash
python -m goalflow.tool.dify_transformer.wf_transformer_tool \
    --dsl path/to/my_flow.yml \
    --out my_flow_workflow.py \
    --class MyFlowWorkflow
```

- `--dsl`(必填)—— 导出文件路径,会校验存在性。
- `--out`(可选)—— 裸文件名会落到 `src/goalflow/workflow/generated/`;传目录或完整路径则写到该处。省略 → `generated/workflow.py`。
- `--class`(可选)—— 生成的类名。

成功后会打印写入的路径。生成文件定义了 `class MyFlowWorkflow(BaseWorkflow[BaseState])`,含 `_setup_nodes` / `_setup_edges` 及变量初始化方法。结构详解见 [dify-transformer.zh-CN.md](dify-transformer.zh-CN.md)。

> [!TIP]
> 也可以用 Python 转译(方便脚本化):
> ```python
> from goalflow.tool.dify_transformer.wf_code_generator import WorkflowCodeGenerator
> written = WorkflowCodeGenerator(
>     "path/to/my_flow.yml",
>     file_name="my_flow_workflow.py",
>     class_name="MyFlowWorkflow",
> ).generate()
> print(written)
> ```

### 1.3 注册工作流

请求通过 [`src/goalflow/api/auth_validator.py`](../src/goalflow/api/auth_validator.py) 中的 **MD5(api_key) → 类** 映射路由到工作流。为你选定的 key 计算哈希:

```bash
python -c "import hashlib; print(hashlib.md5(b'my-secret-key').hexdigest())"
```

然后导入你的类并添加条目:

```python
# src/goalflow/api/auth_validator.py
from goalflow.workflow.generated.my_flow_workflow import MyFlowWorkflow

apikey_workflow_def_map = {
    "<my-secret-key 的 md5 十六进制>": MyFlowWorkflow,
}
```

实例按类惰性创建并缓存;`bind_subworkflows()` 在创建时执行一次。

> [!NOTE]
> 这个代码内静态映射是当前设计,也是真实部署时你首先会替换的东西 —— 见 [design-notes.zh-CN.md](design-notes.zh-CN.md)。

### 1.4 运行并调用

```bash
goalflow-server          # 或:python start_server.py
```

```bash
curl -N http://localhost:8000/v1/chat-messages \
  -H "Authorization: Bearer my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "hello", "user": "user-123", "conversation_id": null, "response_mode": "streaming", "inputs": {}}'
```

你会得到一个 SSE 流(`text/event-stream`),采用 Dify chunk 结构,并带 `X-Workflow-Run-ID` 响应头。把 `response_mode` 改为 `"blocking"` 可得到单个 JSON 响应。完整字段见 [api-reference.zh-CN.md](api-reference.zh-CN.md)。

---

## 教程 2 — 用 `AgentBaseNode` 构建一个 agent 节点

**目标:** 写一个节点,在工作流图内承载一个 `agent_kit` agent 循环(默认是 ReAct 工具调用循环)。

> [!IMPORTANT]
> **代码现状。** `AgentBaseNode`([`src/goalflow/node/agent_base.py`](../src/goalflow/node/agent_base.py))是抽象基类,**仓库内没有任何具体子类** —— 类 docstring 展示了写法,但没有现成示例节点可抄。另外注意 docstring 里的示例方法名(`serialize_output`)已过时;你真正要实现的抽象方法是 **`build_command`**。本教程给出一个对照当前 API 正确的最小子类。(较老的 [`AgentNode`](../src/goalflow/node/agent_node.py) 是**另一条**血脉,直接对接 LangChain、**不**使用 `agent_kit`,别拿它当这里的模板。)

### 2.1 你必须实现什么

`AgentBaseNode(BaseNode, Agent[OutputT])` 同时多继承工作流节点与 kit 的 `Agent`。一个具体子类需实现三个方法:

| 方法 | 来自 | 用途 |
|------|------|------|
| `output_schema(self)` | `Agent`(抽象) | 结构化输出的 Pydantic 类型 |
| `build_prompt(self, state)` | `Agent`(抽象) | 本轮的系统提示词 |
| `build_command(self, state, output)` | `AgentBaseNode`(抽象) | 把 agent 产物翻译为 LangGraph `Command` |

你**不需要**重写 `call` —— `AgentBaseNode` 提供了具体的 `call`,负责搭建流式回调、调用 `Agent.run`,再调用你的 `build_command`。

### 2.2 一个最小 agent 节点

```python
from pydantic import BaseModel
from langgraph.types import Command
from goalflow.node.agent_base import AgentBaseNode


class ClassifyOutput(BaseModel):
    reply: str = ""
    label: str = ""


class CategoryClassifyNode(AgentBaseNode[ClassifyOutput]):
    # `name` 同时是 harness 路由的 task_type、指标前缀与 span 名
    name = "category_classify"

    def output_schema(self):
        return ClassifyOutput

    def build_prompt(self, state):
        return "你是企业服务类目分类器,请简洁作答。"

    def build_command(self, state, output):
        if isinstance(output, ClassifyOutput):
            return Command(
                update={"reply": output.reply, "label": output.label},
                goto=self.next_node_ids,
            )
        # 兜底:模型返回了纯文本
        return Command(update={"reply": str(output)}, goto=self.next_node_ids)
```

**运行时各环节如何串起来:** `BaseNode.__call__` → `AgentBaseNode.call(state)` 读取 `state["sys_query"]` 作为用户查询,接好流式回调,运行 `Agent.run(state, user_query, config=...)`,再把结果交给你的 `build_command`。`Agent.run` 以 `stream_mode="messages"` 驱动已编译的图,返回值要么是一个 `output_schema()` 实例(模型命中结构化响应),要么是最后一段 AI 文本字符串 —— 正好对应上面两个分支。

### 2.3 给 agent 配工具(可选)

默认情况下节点跑的是无工具的裸 ReAct 循环。通过重写 `build_tools_for_agent` 添加工具:

```python
from langchain_core.tools import tool

@tool
def lookup_category(keyword: str) -> str:
    """查询关键词对应的规范类目。"""
    return CATEGORY_DB.get(keyword, "unknown")


class CategoryClassifyNode(AgentBaseNode[ClassifyOutput]):
    name = "category_classify"

    def build_tools_for_agent(self):
        return [lookup_category]

    # output_schema / build_prompt / build_command 同上
```

其他可重写钩子(都有可用默认值):`build_middleware_for_agent`(额外的 `agent_kit` 中间件)、`build_graph_builder_for_agent`(如返回 `DeepGraphBuilder(...)` 以启用子 agent / 记忆,替代默认的 ReAct builder)、`build_harness_for_agent`。

### 2.4 模型解析

构造参数 `llm=`(可选)是三态解析(经 `Agent._resolve_model`):传入具体的 `BaseChatModel` 实例则直接使用;传**字符串**则走 `init_chat_model`;传 `None` 则回退到以 `self.name` 为键的 harness 路由。对工作流节点,通常留空 `llm`,通过 harness/router 配置模型(见 [agent-kit.zh-CN.md](agent-kit.zh-CN.md))。

### 2.5 构造它

`AgentBaseNode` 把 `**kwargs` 转发给 `BaseNode`,后者的必填仅位置外关键字字段是 `desc`、`selected`、`title`、`type`(以及一批可选字段如 `id`、`next_node_ids`)。在生成的工作流里这些来自 `common_args`;独立使用时显式传入:

```python
node = CategoryClassifyNode(
    id="classify-1", desc="", selected=True, title="分类", type="agent",
    next_node_ids=["answer-1"],
)
```

然后像其他节点一样把它加进工作流的 `_setup_nodes` / 图,并在 `_setup_edges` 里路由过去。若要在**转译出的** Dify 流程里使用,这是手工扩展点 —— visitor 生成的是旧版 `AgentNode`,所以基于 `AgentBaseNode` 的节点目前需要你手工接入。

---

## 教程 3 — 实现一个自定义 `DataAdapter`

**目标:** 通过把引擎的中立事件流映射成你自己的帧格式,新增一种面向客户端的通信协议。

> [!IMPORTANT]
> **代码现状。** `DataAdapter` 这一层**已定义,但尚未接入默认请求链路。** 目前 generate 服务(`ChatflowGenerateService` / `WorkflowGenerateService`)通过 `format_stream_chunk(...)` 辅助函数直接产出 SSE,从不调用 adapter;`OpenAIDataAdapter` 在 `app.py` 里只被 import 一次、其余未用。所以本教程分两部分:(A) 写一个满足契约的 adapter,(B) 由你自己接线 —— 接线属于扩展,而非现有行为。随附的 `OpenAIDataAdapter` 还有几处潜在 bug(死分支里调用了未定义的 `self._get_current_timestamp()`、`chunk.meta` 与 `chunk.metadata` 字段名不符、把 dict 塞进 f-string 而非 JSON),请把它当作**形态参考**而非复制源。

### 3.1 契约

`AbstractDataAdapter`([`abstract_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/abstract_data_adapter.py))恰好声明**两个**抽象方法:

```python
class AbstractDataAdapter(ABC):
    @abstractmethod
    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        """流式:把引擎的 SSE 行流转换成你的协议帧。"""

    @abstractmethod
    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        """非流式:把单个响应转换成你的协议形态(一个 dict)。"""
```

- `generate` 接收一个 SSE 行字符串的生成器(每行形如 `data: {...}\n\n`),产出你协议的帧字符串。
- `execute` 接收一个 `ChatCompletionBlockingResponse`(字段含 `answer`、`message_id`、`conversation_id`、`metadata` 等),返回一个 dict。

两个内置实现划出了范围两端:
- `DifyDataAdapter` —— 恒等:`generate` 原样产出每个 chunk,`execute` 返回 `data.model_dump()`。
- `OpenAIDataAdapter` —— 转换:把每个 `data: ` 行解析成 `ChatStreamChunk`,只保留 `message`/`error` 事件,再重新发出 OpenAI 形态的帧。

### 3.2 编写 adapter

把每个进来的 SSE 行解析成 `ChatStreamChunk`,再发出你自己的帧。下例把回答文本包进一个小小的自定义信封:

```python
# src/goalflow/workflow/services/data_adapter/my_data_adapter.py
import json
from typing import Generator

from goalflow.api.base_types import ChatStreamChunk, ChatCompletionBlockingResponse
from goalflow.workflow.services.data_adapter.abstract_data_adapter import AbstractDataAdapter


class MyDataAdapter(AbstractDataAdapter):
    def __init__(self, config: dict = None):
        self.config = config or {}

    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        for raw in generator:
            raw = raw.strip()
            if not raw.startswith("data: "):
                continue
            chunk = ChatStreamChunk.model_validate_json(raw[6:])
            if chunk.event == "message":
                frame = {"type": "token", "text": chunk.answer or ""}
                yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
            elif chunk.event == "error":
                frame = {"type": "error", "message": chunk.message}
                yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
            # 这里忽略 update/done,或按你的协议需要映射它们

    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        return {"type": "final", "text": data.answer, "message_id": data.message_id}
```

注意相对随附 OpenAI adapter 的修正:单空格 `data: ` 前缀、`json.dumps(...)`(而非把裸 dict 放进 f-string)、以及需要逐 chunk 元数据时读 `chunk.metadata`(字段是 `metadata`,不是 `meta`)。

### 3.3 接入端点

由于服务尚未调用 adapter,可在端点处包裹它们的输出。在 [`src/goalflow/app.py`](../src/goalflow/app.py) 里,流式分支当前是:

```python
chat_service = ChatflowGenerateService(workflow)
return StreamingResponse(chat_service.generate(initial_state), media_type="text/event-stream", ...)
```

用你的 adapter 包裹生成器:

```python
adapter = MyDataAdapter()
return StreamingResponse(
    adapter.generate(chat_service.generate(initial_state)),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
             "X-Workflow-Run-ID": workflow_run_id},
)
```

阻塞模式则把响应对象过一遍 `execute`:

```python
result = chat_service.execute(initial_state)          # ChatCompletionBlockingResponse
return adapter.execute(result)                         # 你的 dict 形态
```

更理想的长期落点是放进服务的 `generate`/`execute` **内部**(这样每个端点都统一获得 adapter)—— 这正是 [protocols-and-adapters.zh-CN.md](protocols-and-adapters.zh-CN.md) 里指出的预期集成点。无论哪种方式,因为 adapter 只看到中立事件流,新增协议时你都无需触碰引擎、节点或图。

---

## 运行测试

仓库在 [`test/`](../test/) 下自带单元测试与集成测试:

```bash
# 单元测试(快;多数无需构建 LangGraph 图)
python -m pytest test/unit_tests -q

# 单个节点的测试
python -m pytest test/unit_tests/test_code_node.py -q
```

`test/integration_tests/` 下的集成演示会构建真实的 LangGraph 工作流(`simple_demo.py` 是 `Start → LLM → Answer`);其中多个支持 `--mock` 参数,无需真实 LLM 凭证即可运行。各脚本的运行细节见 [`test/README.md`](../test/README.md)。

---

## 下一步去哪

- 深化对转译器的心智模型 → [dify-transformer.zh-CN.md](dify-transformer.zh-CN.md)
- agent SDK 内部机制(graph builder、中间件、harness)→ [agent-kit.zh-CN.md](agent-kit.zh-CN.md)
- 完整的协议/事件模型 → [protocols-and-adapters.zh-CN.md](protocols-and-adapters.zh-CN.md) 与 [streaming-and-hitl.zh-CN.md](streaming-and-hitl.zh-CN.md)
