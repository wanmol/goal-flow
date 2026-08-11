**English** | [简体中文](tutorials.zh-CN.md)

# End-to-End Tutorials

Three hands-on walkthroughs for the first things most people want to do with goalflow:

1. [Transpile a tiny Dify flow and call it](#tutorial-1--transpile-a-tiny-dify-flow-and-call-it) — the full visual-to-running-server loop.
2. [Build an agent node with `AgentBaseNode`](#tutorial-2--build-an-agent-node-with-agentbasenode) — embed an `agent_kit` loop as a workflow node.
3. [Implement a custom `DataAdapter`](#tutorial-3--implement-a-custom-dataadapter) — add a new wire protocol.

They assume you've done [Getting Started](getting-started.md) (clone, `pip install -e .`, a working `.env`, Redis + MySQL reachable).

> [!NOTE]
> Tutorials 2 and 3 touch parts of the codebase that are **defined but not yet wired into the default request path** (see the honest callouts in each section). They're written so the code you produce is correct against the current APIs, and they mark exactly where you are extending the framework rather than following an existing path.

---

## Tutorial 1 — Transpile a tiny Dify flow and call it

**Goal:** design a minimal chatflow in Dify, transpile the exported DSL into a runnable workflow class, register it, and hit it over HTTP.

### 1.1 Design and export in Dify

In Dify Studio build the smallest useful chatflow:

```
Start → LLM → Answer
```

- **Start** — no config needed.
- **LLM** — pick a model, set the prompt to something like `Answer the user concisely: {{#sys.query#}}`.
- **Answer** — output the LLM node's text.

Export it (`... → Export DSL`) to `my_flow.yml`.

### 1.2 Transpile the DSL to a workflow class

Run the transformer as a module from the project root:

```bash
python -m goalflow.tool.dify_transformer.wf_transformer_tool \
    --dsl path/to/my_flow.yml \
    --out my_flow_workflow.py \
    --class MyFlowWorkflow
```

- `--dsl` (required) — path to the export; validated to exist.
- `--out` (optional) — a bare filename lands in `src/goalflow/workflow/generated/`; a directory or full path writes there instead. Omitted → `generated/workflow.py`.
- `--class` (optional) — the generated class name.

On success it prints the path it wrote. The generated file defines `class MyFlowWorkflow(BaseWorkflow[BaseState])` with `_setup_nodes` / `_setup_edges` / variable setup methods. See [dify-transformer.md](dify-transformer.md#anatomy-of-a-generated-workflow) for the anatomy.

> [!TIP]
> You can transpile from Python instead (handy for scripting):
> ```python
> from goalflow.tool.dify_transformer.wf_code_generator import WorkflowCodeGenerator
> written = WorkflowCodeGenerator(
>     "path/to/my_flow.yml",
>     file_name="my_flow_workflow.py",
>     class_name="MyFlowWorkflow",
> ).generate()
> print(written)
> ```

### 1.3 Register the workflow

A request is routed to a workflow by an **MD5(api_key) → class** map in [`src/goalflow/api/auth_validator.py`](../src/goalflow/api/auth_validator.py). Compute the hash for a key you choose:

```bash
python -c "import hashlib; print(hashlib.md5(b'my-secret-key').hexdigest())"
```

Then import your class and add the entry:

```python
# src/goalflow/api/auth_validator.py
from goalflow.workflow.generated.my_flow_workflow import MyFlowWorkflow

apikey_workflow_def_map = {
    "<md5-hex-of-my-secret-key>": MyFlowWorkflow,
}
```

Instances are created lazily and cached per class; `bind_subworkflows()` runs once at creation.

> [!NOTE]
> This static in-code map is the current design and the first thing you'll replace for a real deployment — see [design-notes.md](design-notes.md#authentication--workflow-registration).

### 1.4 Run and call it

```bash
goalflow-server          # or: python start_server.py
```

```bash
curl -N http://localhost:8000/v1/chat-messages \
  -H "Authorization: Bearer my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "hello", "user": "user-123", "conversation_id": null, "response_mode": "streaming", "inputs": {}}'
```

You get an SSE stream (`text/event-stream`) with the Dify chunk shape and an `X-Workflow-Run-ID` header. Switch `response_mode` to `"blocking"` for a single JSON response. Full field list in [api-reference.md](api-reference.md#post-v1chat-messages).

---

## Tutorial 2 — Build an agent node with `AgentBaseNode`

**Goal:** write a node that hosts an `agent_kit` agent loop (a ReAct tool-use loop by default) inside a workflow graph.

> [!IMPORTANT]
> **Current state.** `AgentBaseNode` ([`src/goalflow/node/agent_base.py`](../src/goalflow/node/agent_base.py)) is an abstract base with **no concrete subclass in the repo** — the class docstring shows the pattern, but there is no ready-made example node to copy. Also note the docstring's example method name (`serialize_output`) is stale; the real abstract method you must implement is **`build_command`**. This tutorial gives you a correct, minimal subclass against the current API. (The older [`AgentNode`](../src/goalflow/node/agent_node.py) is a *separate* lineage that talks to LangChain directly and does **not** use `agent_kit` — don't use it as the template here.)

### 2.1 What you must implement

`AgentBaseNode(BaseNode, Agent[OutputT])` multiply-inherits the workflow node and the kit's `Agent`. A concrete subclass implements three methods:

| Method | Comes from | Purpose |
|--------|-----------|---------|
| `output_schema(self)` | `Agent` (abstract) | the structured-output Pydantic type |
| `build_prompt(self, state)` | `Agent` (abstract) | system prompt for this turn |
| `build_command(self, state, output)` | `AgentBaseNode` (abstract) | translate the agent's product into a LangGraph `Command` |

You do **not** override `call` — `AgentBaseNode` provides a concrete `call` that sets up the stream callback, invokes `Agent.run`, and then calls your `build_command`.

### 2.2 A minimal agent node

```python
from pydantic import BaseModel
from langgraph.types import Command
from goalflow.node.agent_base import AgentBaseNode


class ClassifyOutput(BaseModel):
    reply: str = ""
    label: str = ""


class CategoryClassifyNode(AgentBaseNode[ClassifyOutput]):
    # `name` doubles as the harness router task_type, metric prefix, and span name
    name = "category_classify"

    def output_schema(self):
        return ClassifyOutput

    def build_prompt(self, state):
        return "You are an enterprise-service category classifier. Reply concisely."

    def build_command(self, state, output):
        if isinstance(output, ClassifyOutput):
            return Command(
                update={"reply": output.reply, "label": output.label},
                goto=self.next_node_ids,
            )
        # fallback: model returned plain text
        return Command(update={"reply": str(output)}, goto=self.next_node_ids)
```

**How the pieces flow at runtime:** `BaseNode.__call__` → `AgentBaseNode.call(state)` reads `state["sys_query"]` as the user query, wires a stream callback, runs `Agent.run(state, user_query, config=...)`, and hands the result to your `build_command`. `Agent.run` drives the compiled graph with `stream_mode="messages"` and returns either an `output_schema()` instance (when the model produced a structured response) or the last AI text string — which is exactly the two branches above.

### 2.3 Giving the agent tools (optional)

By default the node runs a bare ReAct loop with no tools. Add tools by overriding `build_tools_for_agent`:

```python
from langchain_core.tools import tool

@tool
def lookup_category(keyword: str) -> str:
    """Look up the canonical category for a keyword."""
    return CATEGORY_DB.get(keyword, "unknown")


class CategoryClassifyNode(AgentBaseNode[ClassifyOutput]):
    name = "category_classify"

    def build_tools_for_agent(self):
        return [lookup_category]

    # output_schema / build_prompt / build_command as above
```

Other overridable hooks (all with working defaults): `build_middleware_for_agent` (extra `agent_kit` middleware), `build_graph_builder_for_agent` (e.g. return `DeepGraphBuilder(...)` for sub-agents/memory instead of the default ReAct builder), and `build_harness_for_agent`.

### 2.4 Model resolution

The optional `llm=` constructor argument is tri-state (via `Agent._resolve_model`): a concrete `BaseChatModel` instance is used as-is; a model **string** goes through `init_chat_model`; `None` falls back to the harness router keyed by `self.name`. For a workflow node you usually leave `llm` unset and configure the model through the harness/router (see [agent-kit.md](agent-kit.md#harness-governance-container)).

### 2.5 Constructing it

`AgentBaseNode` forwards `**kwargs` to `BaseNode`, whose required keyword-only fields are `desc`, `selected`, `title`, `type` (plus many optional ones like `id`, `next_node_ids`). In a generated workflow these come from `common_args`; standalone you pass them explicitly:

```python
node = CategoryClassifyNode(
    id="classify-1", desc="", selected=True, title="Classify", type="agent",
    next_node_ids=["answer-1"],
)
```

Then add it to your workflow's `_setup_nodes` / graph like any other node, and route to it in `_setup_edges`. To use it in a *transpiled* Dify flow, this is the manual extension point — the visitor emits the legacy `AgentNode`, so an `AgentBaseNode`-based node is something you wire in by hand today.

---

## Tutorial 3 — Implement a custom `DataAdapter`

**Goal:** add a new client-facing wire protocol by mapping the engine's neutral event stream to your own frame format.

> [!IMPORTANT]
> **Current state.** The `DataAdapter` layer is **defined but not yet wired into the default request path.** The generate services (`ChatflowGenerateService` / `WorkflowGenerateService`) currently emit SSE directly via a `format_stream_chunk(...)` helper and never call an adapter; `OpenAIDataAdapter` is imported once in `app.py` and otherwise unused. So this tutorial has two parts: (A) write an adapter that satisfies the contract, and (B) wire it in yourself — that wiring is the extension, not existing behavior. The shipped `OpenAIDataAdapter` also has a few latent bugs (an undefined `self._get_current_timestamp()` in a dead branch, a `chunk.meta` vs `chunk.metadata` field mismatch, and a dict interpolated into an f-string instead of JSON), so read it as a shape reference, not a copy source.

### 3.1 The contract

`AbstractDataAdapter` ([`abstract_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/abstract_data_adapter.py)) declares exactly **two** abstract methods:

```python
class AbstractDataAdapter(ABC):
    @abstractmethod
    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        """Streaming: transform the engine's SSE line stream into your wire frames."""

    @abstractmethod
    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        """Blocking: transform a single response into your wire shape (a dict)."""
```

- `generate` receives a generator of raw SSE line strings (each like `data: {...}\n\n`) and yields your protocol's frames as strings.
- `execute` receives a `ChatCompletionBlockingResponse` (fields include `answer`, `message_id`, `conversation_id`, `metadata`, …) and returns a dict.

The two built-ins bracket the range:
- `DifyDataAdapter` — identity: `generate` yields each chunk unchanged, `execute` returns `data.model_dump()`.
- `OpenAIDataAdapter` — transforms: parses each `data: ` line into a `ChatStreamChunk`, keeps only `message`/`error` events, and re-emits OpenAI-shaped frames.

### 3.2 Write the adapter

Parse each incoming SSE line into a `ChatStreamChunk`, then emit your own frames. This example wraps the answer text in a tiny custom envelope:

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
            # ignore update/done here, or map them if your protocol needs them

    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        return {"type": "final", "text": data.answer, "message_id": data.message_id}
```

Note the fixes relative to the shipped OpenAI adapter: a single-space `data: ` prefix, `json.dumps(...)` (not a bare dict in an f-string), and reading `chunk.metadata` if you need per-chunk metadata (the field is `metadata`, not `meta`).

### 3.3 Wire it into an endpoint

Because the services don't call an adapter yet, wrap their output at the endpoint. In [`src/goalflow/app.py`](../src/goalflow/app.py), the streaming branch currently does:

```python
chat_service = ChatflowGenerateService(workflow)
return StreamingResponse(chat_service.generate(initial_state), media_type="text/event-stream", ...)
```

Wrap the generator with your adapter:

```python
adapter = MyDataAdapter()
return StreamingResponse(
    adapter.generate(chat_service.generate(initial_state)),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
             "X-Workflow-Run-ID": workflow_run_id},
)
```

For blocking mode, pass the response object through `execute`:

```python
result = chat_service.execute(initial_state)          # ChatCompletionBlockingResponse
return adapter.execute(result)                         # your dict shape
```

The cleaner long-term home for this is *inside* the service's `generate`/`execute` (so every endpoint gets the adapter uniformly) — that's the intended integration point noted in [protocols-and-adapters.md](protocols-and-adapters.md#writing-a-custom-adapter). Either way, because the adapter only ever sees the neutral event stream, you never touch the engine, nodes, or graph to add a protocol.

---

## Running the tests

The repo ships unit and integration tests under [`test/`](../test/):

```bash
# unit tests (fast, no LangGraph graph build required for most)
python -m pytest test/unit_tests -q

# a single node's tests
python -m pytest test/unit_tests/test_code_node.py -q
```

Integration demos under `test/integration_tests/` build real LangGraph workflows (`simple_demo.py` is `Start → LLM → Answer`); several support a `--mock` flag so they run without live LLM credentials. See [`test/README.md`](../test/README.md) for the per-script runner details.

---

## Where to go next

- Deepen the transpiler mental model → [dify-transformer.md](dify-transformer.md)
- The agent SDK internals (graph builders, middleware, harness) → [agent-kit.md](agent-kit.md)
- The full protocol/event model → [protocols-and-adapters.md](protocols-and-adapters.md) and [streaming-and-hitl.md](streaming-and-hitl.md)
