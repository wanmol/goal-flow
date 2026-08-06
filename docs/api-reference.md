**English** | [简体中文](api-reference.zh-CN.md)

# API Reference

All endpoints are defined in [`app.py`](../src/goalflow/app.py) and the routers under [`api/`](../src/goalflow/api/). Authenticated workflow endpoints expect:

```
Authorization: Bearer <api_key>
```

The key is MD5-hashed and looked up in `apikey_workflow_def_map` to resolve the target workflow instance (see [getting-started.md](getting-started.md#5-register-a-workflow)).

Optional tracing headers propagate a distributed trace: an upstream request-id header and upstream `trace_id` / `span_id` headers (constants `WF_REQUEST_ID_HEADER_NAME`, `UPSTREAM_TRACE_ID_HEADER_NAME`, `UPSTREAM_SPAN_ID_HEADER_NAME`).

## Chat & workflow

### `POST /v1/chat-messages`

Run a **chatflow** (workflow type must be `chatflow`). Supports streaming and blocking.

Request body (`WorkflowInput`):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `query` | string | `""` | user message |
| `user` | string | **required** | user id |
| `conversation_id` | string? | `null` | omit to start a new conversation |
| `response_mode` | string | `"streaming"` | `streaming` or `blocking` |
| `scene_type` | string? | `null` | |
| `sys_app_id` | string | `"aira-workflow"` | |
| `sys_workflow_id` | string | (default id) | |
| `files` | list? | `null` | uploaded files |
| `inputs` | object | `{}` | workflow input variables (e.g. `use_end_stream`) |

- **Streaming** → `text/event-stream` (SSE). Response header `X-Workflow-Run-ID` carries the run id. Frames follow the active [data adapter](protocols-and-adapters.md); default is the Dify chunk shape (`chunk_id`, `type`, `data`, `timestamp`), with lifecycle types `workflow_started` / `node_finished` / `text_chunk` / `error` / `done`.
- **Blocking** → single JSON response.

### `POST /v1/chat-messages/{task_id}/stop`

Set the Redis stop flag for a running task so its stream terminates. Returns `{"success": true, ...}`.

### `POST /v1/workflows/run`

Run a **workflow** type (non-chat). Same streaming/blocking model via `WorkflowGenerateService`.

### `POST /v1/chat/completions`

**OpenAI-compatible** chat endpoint (added for LLM-application filing/compliance). Accepts a `ChatCompletionRequest`; responses use `OpenAIDataAdapter` (`chat.completion.chunk` streaming or a `chat.completion` object). Lets OpenAI-API clients drive your workflows. See [protocols-and-adapters.md](protocols-and-adapters.md#the-included-alternative-openai-compatible).

### `POST /v1/images/generations`

Generate an image (`ImageGenerationRequest` → `ImageGenerationResponse`). Downloads the generated image, applies a watermark, uploads to OSS, and returns the CDN URL. Requires the image-generation and `OSS_PUBLIC_*` env config.

## Suggested questions

### `POST /v1/messages/{message_id}/suggested`

Generate follow-up question suggestions from recent conversation history. Body may include `tpl_id` to select a prompt template (`suggest_q_tpl_map`). Query param `user` required. Returns `{"result": "success", "data": [...]}`.

### `GET /v1/messages/{message_id}/suggested`

Same purpose, GET variant with default prompt template. Query param `user` required.

## Human-in-the-Loop — `src/goalflow/api/hitl_api.py`

Router prefix **`/api/v1/hitl`**. See [streaming-and-hitl.md](streaming-and-hitl.md#human-in-the-loop-hitl).

| Method & path | Purpose |
|---------------|---------|
| `GET /reviews/{review_id}` | Get a review's detail |
| `GET /workflows/{workflow_run_id}/reviews` | List all reviews for a run |
| `POST /reviews/approve` | Approve a review (resumes the workflow) |
| `POST /reviews/modify` | Approve with modifications |
| `POST /reviews/reject` | Reject a review |
| `POST /workflows/{workflow_run_id}/resume` | Manually resume a paused workflow |
| `GET /health` | HITL health check |

## Reports — `src/goalflow/api/report_api.py`

Router prefix **`/v1/reports`**. Backed by `src/goalflow/service/report_service.py`.

| Method & path | Purpose |
|---------------|---------|
| `POST /list` | List reports |
| `POST /detail` | Get a report's detail |
| `POST /versions` | List a report's versions |

## Health & diagnostics

| Method & path | Purpose |
|---------------|---------|
| `GET /` | Root/liveness |
| `GET /health` | Health check |
| `GET /middle_health` | Middleware (Redis/MySQL) health check |
| `GET /memory-intensive` | Test endpoint for the memory monitor |
| (memory routers) | Diagnostic routes registered from `src/goalflow/monitor/memory_routes*.py` |

## Notes on the current API surface

- Two functions named `stream_workflow` decorate both `/v1/chat-messages` and `/v1/chat/completions`; the shadowing is harmless to FastAPI (each decorator registers independently) but confusing to readers.
- The exception handlers for `WorkflowError` / `StateValidationError` return a dict with a `status_code` field rather than setting the HTTP status; consider returning a proper `JSONResponse`. See [design-notes.md](design-notes.md).
