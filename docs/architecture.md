**English** | [简体中文](architecture.zh-CN.md)

# Architecture

This framework layers a workflow/agent engine on top of LangGraph and exposes it over HTTP with a pluggable wire protocol. This page explains how the pieces fit and how a request flows through them.

## The core idea

LangGraph gives you a `StateGraph`: nodes that read and write a shared state, connected by edges. This framework adds, on top of that:

1. A **library of ready-made nodes** (`src/goalflow/node/`) that mirror the building blocks visual tools like Dify expose — LLM, code, HTTP, if/else, classifier, iteration, loop, tool, agent, and more.
2. A **transpiler** (`src/goalflow/tool/dify_transformer/`) that turns a Dify DSL export into a `BaseWorkflow` subclass wiring those nodes together, so you design visually but run on your own LangGraph.
3. A **serving + streaming layer** (`src/goalflow/workflow/services/`, `src/goalflow/workflow/chunk_processor/`, `src/goalflow/workflow/stream/`) that drives the graph, converts LangGraph's raw stream into semantic events, and emits them over SSE.
4. A **protocol abstraction** (`src/goalflow/workflow/services/data_adapter/`) so the events can be serialized to whatever wire format the client expects (Dify by default, OpenAI-compatible included).
5. An **agent SDK** (the vendored `agent_kit` package) for real agent loops (ReAct / Deep / custom), integrated into the node layer via `src/goalflow/node/agent_base.py`.

## Component map

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

## Request lifecycle (streaming chatflow)

Following `POST /v1/chat-messages` in [`app.py`](../src/goalflow/app.py):

1. **Auth & routing.** `validate_token_and_get_wf` reads `Authorization: Bearer <key>`, MD5-hashes the key, looks it up in `apikey_workflow_def_map`, and returns a cached `BaseWorkflow` instance. Wrong type → 500 (`/v1/chat-messages` requires a `chatflow`).
2. **Request context.** A `request_id` is taken from the `X-Request-Id`-style header (or generated) and stored in a `contextvar`. Upstream `trace_id`/`span_id` headers are captured into the trace context so spans chain across services.
3. **Initial state.** `prepare_initial_state` maps the request body into a `BaseState` dict: `sys_query`, `sys_user_id`, `sys_app_id`, `sys_workflow_id`, `sys_conversation_id`, `sys_files`, `input_variables`, etc. A fresh `sys_workflow_run_id` (UUID) is assigned.
4. **Drive the graph.** `ChatflowGenerateService(workflow).generate(initial_state)` is returned as a `StreamingResponse` (`media_type="text/event-stream"`). Internally it iterates the stream processor over `workflow.stream(...)`, which calls LangGraph's `compiled_graph.stream(stream_mode=["updates","messages","custom"])`.
5. **Semantic events.** The chunk processor decides, per token, whether the emitting node provably reaches an `answer`/`end` node (branch-aware routing) and emits typed events. It handles `<think>` reasoning tags, token-usage extraction, interrupts (HITL), and control events.
6. **Wire format.** Events pass through the active `DataAdapter` and are serialized as SSE frames.
7. **Persistence & stop.** Messages are written to Redis + MySQL; every N chunks the service checks a Redis stop flag so `POST /v1/chat-messages/{task_id}/stop` can abort mid-stream.

The blocking path (`response_mode="blocking"`) calls `execute()`/`.invoke()` and returns a single JSON response instead of a stream.

## The node execution model

Every node is a `BaseNode` subclass and a LangGraph-callable (`__call__`). The one method subclasses implement is `call(state) -> NodeOutput`. Around it, `BaseNode.__call__` provides a uniform lifecycle:

- **"node started" log** → **`pre_call` fan-in barrier** → **`call`** → **output truncation** → **"node finished" log** → **`step` bump**.
- **Routing** is expressed by the return value: a dict updates state; a `Command(update=..., goto=...)` updates and jumps; a `List[str]` selects branches; a `Sequence[Send]` fans out (map-reduce, used by iteration).
- **Fan-in synchronization** uses `node_level` (topological depth, assigned by `_analysis_node_level`) together with a `step` counter: a node with multiple predecessors re-queues itself until all upstream branches have advanced, so it runs once with complete inputs.
- **Error strategy** is per-node: `default-value` (emit a fallback and continue) or `fail-branch` (route down `fail_branch_node_ids`).

Full details and every node's config are in [nodes.md](nodes.md); the state schema and reducers are in [storage-and-config.md](storage-and-config.md#state).

## Graph vs. loop — and combining them

- A **workflow graph** is great for explicit, auditable control flow but awkward for open-ended reasoning.
- An **agent loop** (ReAct/Deep) is great for open-ended tool use but harder to constrain and observe step-by-step.

The framework lets you combine them:

- An **`AgentNode` / `AgentBaseNode`** embeds an agent loop inside a graph node. `AgentBaseNode` (see [`agent_base.py`](../src/goalflow/node/agent_base.py)) multiply-inherits `BaseNode` and the vendored `agent_kit`'s `Agent`, so an agent loop is just another node in your LangGraph, streaming tokens through the same pipeline.
- A workflow can be bound as a **sub-workflow** and invoked from within another (via `bind_subworkflows()` and the sub-workflow bridging fields in state), so agents can call structured flows as tools and vice versa.

See [agent-kit.md](agent-kit.md) for the agent side.

## Where to go next

| To understand… | Read |
|----------------|------|
| Each node type | [nodes.md](nodes.md) |
| Turning Dify DSL into a workflow | [dify-transformer.md](dify-transformer.md) |
| Swapping the wire protocol | [protocols-and-adapters.md](protocols-and-adapters.md) |
| Token streaming & HITL internals | [streaming-and-hitl.md](streaming-and-hitl.md) |
| State fields, Redis/MySQL, config | [storage-and-config.md](storage-and-config.md) |
| The agent SDK | [agent-kit.md](agent-kit.md) |
