**English** | [简体中文](agent-kit.zh-CN.md)

# Agent Kit (`agent_kit`)

`agent_kit` is a framework-agnostic SDK for building **agent loops** on LangGraph. It's vendored here as a package at `src/agent_kit/` and provides the agent runtime, a middleware pipeline, model routing/failover, an executable-skills system, and observability — all behind a small `Agent` base class.

> The SDK is vendored directly into this repo at `src/agent_kit/`. Publishing it as a standalone dependency (e.g. on PyPI) is on the roadmap — see [design-notes.md](design-notes.md#agent-kit-integration).

## Why a separate kit

Plain workflow graphs are great for explicit control flow; plain agent loops are great for open-ended tool use. Neither alone covers everything, so the kit is designed to slot **into** the workflow as a node (via `src/goalflow/node/agent_base.py`), letting you mix `graph + loop`. See [architecture.md](architecture.md#graph-vs-loop--and-combining-them).

## The `Agent` class

`Agent[OutputT]` (`src/agent_kit/agent.py`) is the public entry point. You subclass it and implement a small set of hooks:

| Hook | Required | Purpose |
|------|----------|---------|
| `output_schema()` | yes | structured output type (Pydantic) |
| `build_prompt(state)` | yes | system prompt for this turn |
| `format_user_input()` | no | shape the user message |
| `format_output()` | no | post-process the final answer |

Construction accepts `model`, `tools`, `subagents`, `middleware=[...]`, `graph_builder`, `harness`, and `cache_graph`.

Model resolution (`_resolve_model`) is tri-state: an explicit `BaseChatModel` > a model string (`init_chat_model`) > the harness router (`harness.router.get(self.name)`).

`run(state, user_query, config)` compiles the graph, builds the prompt, drives `graph.stream(stream_mode="messages")`, pushes each `AIMessageChunk` to `config.configurable["stream_callback"]`, and returns the `structured_response` (or last AI text via `format_output`).

## Graph builders (agent topologies)

The `GraphBuilder` protocol (`src/agent_kit/graphs/base.py`) has one method: `build(*, model, tools, middleware, output_schema, **extra)`. Three implementations:

| Builder | Wraps | Use for |
|---------|-------|---------|
| `ReactGraphBuilder` (`react.py`) | `langchain.agents.create_agent` | standard ReAct tool-use loop (default) |
| `DeepGraphBuilder` (`deep.py`) | `deepagents.create_deep_agent` | sub-agents, memory (AGENTS.md), HITL `interrupt_on` |
| `CustomGraphBuilder` (`custom.py`) | your `builder_fn` | hand-built `StateGraph` |

`Agent` auto-selects `DeepGraphBuilder` when `subagents` are present (injecting `SubAgentInitializeMiddleware`), otherwise `ReactGraphBuilder`.

## Middleware pipeline

Middleware (`src/agent_kit/middleware/`) runs in list order and replaces the older per-runtime hooks. They fall into two groups:

**Constraint / control**
- `EntryGuardMiddleware` — gate whether the agent runs at all.
- `ModelSkipMiddleware` — skip the model call under conditions.
- `ModelFailoverMiddleware` — fall back to another model on failure.
- `FallbackReplyMiddleware` — canned reply when everything fails.
- `SensitiveCheckMiddleware` — content safety.

**Enhancement**
- `ConversationHistoryMiddleware` — inject prior turns.
- `SkillAugmentationMiddleware` — match + inject skills (see below).
- `MetricsMiddleware` — emit metrics.
- `StreamingBridgeMiddleware` — bridge tokens to the workflow's stream.
- `LangfuseTracingMiddleware` — tracing spans.

Plus `SubAgentInitializeMiddleware` and the factory `make_dynamic_prompt_middleware`.

## Harness (governance container)

The `Harness` dataclass (`src/agent_kit/harness/`) is an injectable container of cross-cutting services:

- `HarnessSettings` (`settings.py`) — `LLMDefaults` (provider `qwen`, model `qwen-plus`, temp, timeout, retries), observability, fallback-reply settings.
- `ModelRouter` (`model_router.py`) — maps `task_type → LLM`. `register_llm_factory()` injects the LLM factory (the kit stays LLM-agnostic), `configure(task_type, ...)` sets per-task config, `get()` resolves with caching, and `register_fallback_factory()` provides failover.
- `PromptRegistry` — named prompts.
- `HarnessProfile` / `ProfileRegistry` (`profiles.py`) — one call registers an LLM + sub-LLMs + prompts + `skills_dir` + skill-match params, fanning out to the router and prompt registry.
- `tracer` — observability hook.

`default_harness()` binds to process-wide `HARNESS_*` singletons (shared state); a bare `Harness()` is isolated (handy for tests).

## Skills (executable)

The kit's skill system (`src/agent_kit/skills/`) mirrors the main-project [skills engine](skills.md) but supports three modes:

- **prompt-only** — inject instructions (like the main-project engine),
- **executable** — a `module:func` reference materialized as a LangChain `Tool` the agent can call,
- **hybrid** — both.

Enable via `SkillAugmentationMiddleware` or a `HarnessProfile(skills_dir=...)`.

## Integration with the workflow layer

`src/goalflow/node/agent_base.py::AgentBaseNode(BaseNode, Agent[OutputT])` (ADR-004) multiply-inherits the workflow `BaseNode` and the kit's `Agent`. It adds one hook:

```python
def build_command(self, state, output) -> Command:
    """Translate the agent's output into a LangGraph Command (state update + routing)."""
```

`BaseNode.call(state)` sets up a `stream_callback` (via `RunnableConfig.configurable`, guarded by a `ContextVar` for per-request isolation), calls `Agent.run`, then `build_command`. It uses `default_harness()` to share the `HARNESS_*` singletons, and `src/goalflow/node/_harness_bootstrap.py::ensure_harness_wired()` (idempotent) wires this repo's `LLM` factory, metrics, and Langfuse into those singletons.

`AgentBaseNode` supersedes three deprecated bases (`DeepAgentBaseNode`, `CreateAgentBaseNode`, `StateGraphBaseNode`). To build a new agent node, subclass `AgentBaseNode` and implement `output_schema`, `build_prompt`, and `build_command`.

## Learning path

- The vendored package's own `src/agent_kit/README.md` has the SDK-focused walkthrough.
- Runnable examples live in `src/agent_kit/examples/` (`minimal_agent.py`, `conversation_agent.py`, `full_governance.py`, `harness_e2e.py`, `minimal_deep_agent.py`, …).
- Tests in `src/agent_kit/tests/` double as behavior specs for each middleware and builder.
