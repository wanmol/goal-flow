**English** | [简体中文](streaming-and-hitl.zh-CN.md)

# Streaming & Human-in-the-Loop

This page explains how tokens stream out of the engine and how a workflow can pause for human input mid-run.

## The three-layer streaming pipeline

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

### Layer 1 — the engine (`BaseWorkflow.stream`)

`BaseWorkflow.stream(initial_state, config, stream_mode)` calls LangGraph's `compiled_graph.stream(...)` and yields raw `(stream_mode, event_data)` tuples. It runs with a `RunnableConfig` carrying `recursion_limit=500`, `max_concurrency=6`, trace metadata, and a `thread_id` (checkpoint key). Two LangGraph stream modes carry the interesting data:

- **`messages`** — token-by-token output from LLM nodes.
- **`updates`** — node-completion snapshots.
- **`custom`** — interrupts, control events, and passthrough data.

### Layer 2 — chunk processors (`workflow/chunk_processor/`)

The processors convert raw tuples into the typed semantic events in `workflow/stream/types.py`:
`NodeRunStreamChunkEvent`, `NodeRunSucceededEvent`, `NodeRunInterruptEvent`, `NodeRunControlEvent`, `ProxyStreamDataChunk`.

Two processors, one per workflow kind:

- **`WorkflowStreamProcessor`** — routes streamed tokens toward `end` nodes.
- **`ChatflowStreamProcessor`** — routes streamed tokens toward `answer` nodes; also handles interrupts, control events, and passthrough via the `custom` mode.

**Branch-aware streaming** is the clever part. On a `messages` event, the processor looks at `metadata["langgraph_node"]` to find which node emitted the token, then checks whether that node *provably reaches* an `answer`/`end` node given the branches already taken. Only then are tokens forwarded. `_remove_dependencies` prunes edges from branch nodes (`if-else`, `question-classifier`, `fail-branch`) so a token from the *untaken* branch is never streamed to the user. On `updates`, it emits `NodeRunSucceededEvent`, advances the route position, and flushes any static template text for finished `end`/`answer` dependencies.

It also handles:
- **Reasoning tags** — `<think>` / `</think>` content is separated (keys `THINK_START_TAG`, `THINK_END_TAG`, `THINKING_CONTENT_KEY` = `reasoning_content`).
- **Token usage** — extracted when `finish_reason == "stop"`.

### Layer 3 — generate services (`workflow/services/`)

`WorkflowGenerateService.generate(initial_state)` / `ChatflowGenerateService.generate(initial_state)` are generators that:

1. set the `request_id` contextvar and assign `sys_workflow_run_id`,
2. yield a `workflow_started` chunk,
3. build the `RunnableConfig`,
4. iterate the stream processor over `workflow.stream(...)`, mapping semantic events to client chunks:
   - `NodeRunSucceededEvent` → `node_finished` (unwraps `output_variables`),
   - `NodeRunStreamChunkEvent` → `text_chunk`,
5. every `STREAM_OUTPUT_STOP_CHECK_INTERVAL` chunks, check a Redis stop flag so the run can be aborted.

Finally, the chunks pass through the active [DataAdapter](protocols-and-adapters.md) and are written as SSE frames (`data: {...}\n\n`).

### Stopping a run

`POST /v1/chat-messages/{task_id}/stop` sets a Redis flag (`generate_task_stopped:<id>`). The generate service polls it and terminates the stream. This is why long generations can be cancelled from the client.

## Human-in-the-Loop (HITL)

HITL lets a workflow **pause, ask a human, and resume** — for approvals, corrections, or clarifications.

### How a pause works

- A node raises a LangGraph **interrupt**. Because the graph is compiled with a **checkpointer** (MySQL, keyed by `thread_id`), its full state is persisted at the interrupt point.
- The chunk processor surfaces this as a `NodeRunInterruptEvent`, which the service streams to the client as an interrupt chunk (the client learns what input is needed).

### How a resume works

- The client submits the human decision to the HITL API ([`api/hitl_api.py`](../api/hitl_api.py)).
- `BaseWorkflow.resume(resume_data, config)` issues a LangGraph `Command(resume=...)` against the same `thread_id`, so execution continues from exactly where it paused — no re-running earlier nodes.
- Decisions are recorded via the HITL service (`workflow/services/workflow_hitl_service.py`) and persisted (`db/hitl_review.py`). Decision types include `approve` / `reject` / `modify` (see `constants.py`).

### Control events

`NodeRunControlEvent` (from the `custom` stream mode, event name `WF_NODE_CONTROL_EVENT_NAME`) lets the workflow tell the frontend to do things like **clear the current output and regenerate** — useful when a HITL correction invalidates what was already streamed.

## Checkpointing

The checkpointer is the backbone of both stop/resume and HITL. It's managed by `workflow/utils/checkpointer_manager.py` (with `connection_wrapper.py` for the MySQL connection), using `langgraph-checkpoint-mysql`. Each run gets a `thread_id`; state is snapshotted at each super-step so a run can be paused, inspected, and resumed durably.

See [storage-and-config.md](storage-and-config.md) for the persistence layout and [api-reference.md](api-reference.md) for the HITL endpoints.
