**English** | [简体中文](storage-and-config.zh-CN.md)

# Storage & Configuration

This page covers the shared graph **state**, the **Redis + MySQL** persistence design, and how **config / environment variables** are loaded.

## State

`BaseState` (`src/goalflow/state/__init__.py`) is the `TypedDict` every node reads and writes; `GenericState = TypeVar(bound=BaseState, covariant=True)` is the generic used by `BaseNode`/`BaseWorkflow`.

### System fields

Seeded from the request in `src/goalflow/app.py::prepare_initial_state`:

`sys_query`, `sys_user_id`, `sys_app_id`, `sys_workflow_id`, `sys_workflow_run_id`, `sys_conversation_id`, `sys_dialogue_count`, `sys_files`, `sys_scene_type`, `sys_use_end_stream`, `sys_current_date`, `sys_current_datetime`.

### Routing / runtime fields

`node_id`, `source_handle`, `step`, `iteration_round`, `request_id`, `rt_thread_id` (checkpoint key).

### Variable pools

Four pools, plus the final output, each with a **reducer** that controls how concurrent writes merge:

| Field | Reducer | Notes |
|-------|---------|-------|
| `input_variables` | `update_vars` (shallow merge) | request inputs + start-node vars |
| `output_variables` | `update_vars` | per-node outputs, prefixed by node id |
| `conversation_variables` | `update_vars` | loaded from / persisted to DB |
| `environment_variables` | `update_vars` | from the DSL |
| `outputs` | — | final workflow output (from `end`) |
| `node_span_ids` | `deep_merge_vars` (recursive) | trace spans; deep-merge so parallel nodes don't clobber nested `upstreams` |

Reducers defined in `src/goalflow/state/`: `persist_value` (keep the checkpoint value when a node writes `None`), `update_vars` (shallow), `deep_merge_vars` (recursive). Most scalar routing fields use LangGraph's `AnyValue`/`LastValue` channels.

### Sub-workflow & HITL fields

`_sub_workflow_caller_node_id` / `_sub_workflow_caller_span_id` bridge a parent graph to a bound sub-workflow. `hitl_*` fields carry human-in-the-loop review state.

> [!NOTE]
> `BaseState` also carries a large block of **domain-specific fields** for financial-report analysis (`rewritten_query`, `question_type`, `classification_result`, `core_view`, `*_period_analysis`, …). These are an artifact of the framework's origin and should be decoupled from the generic base for a clean open-source core — see [design-notes.md](design-notes.md#domain-fields-in-state).

## Conversation persistence: Redis + MySQL

The design splits **hot** and **durable** storage:

```
        write path
request ─────────────► Redis (fast)  ──► MySQL (durable)
                       cache/            db/
```

### Redis (`src/goalflow/cache/`)

- `redis_manager.py::RedisClusterManager` — connection lifecycle (`init_cluster()` / `close()`), supports cluster and standalone (`REDIS_MODEL`). Toggle the whole layer with `REDIS_ENABLED`.
- `message_cache.py` — hot message cache (recent turns), TTL via `CACHE_DEFAULT_TIMEOUT`.
- `workflow_conversation_variables_cache.py` — cached conversation variables.
- `base_cache.py` — shared cache helpers.
- Also stores **task stop flags** (`generate_task_stopped:<id>`) for stream cancellation.

### MySQL models (`src/goalflow/model/`)

SQLAlchemy models (the pooled engine lives in `src/goalflow/infra/`):

- `message.py` — durable conversation messages.
- `workflow_conversation_variables.py` — durable conversation variables.
- `hitl_review.py` — human-in-the-loop review records.
- MySQL also backs the **LangGraph checkpointer** (`langgraph-checkpoint-mysql`) used for streaming stop/resume and HITL (see [streaming-and-hitl.md](streaming-and-hitl.md#checkpointing)).

### Infra / connection layer (`src/goalflow/infra/`)

Low-level MySQL/Redis connectivity, shared by the model and cache layers:

- `database.py::Database` — pool lifecycle (`init()` / `close()`), sized by `POOL_SIZE`, `MAX_OVERFLOW`, `POOL_RECYCLE`, `POOL_PRE_PING`, `POOL_TIMEOUT`; `Config` holds MySQL + Redis env config.
- `redis_manager.py::RedisClusterManager` — Redis cluster client + `redis_client` singleton.
- `base_cache.py` — shared cache helpers.
- `connection_wrapper.py` / `checkpointer_manager.py` — pooled connection + LangGraph checkpointer for streaming/HITL.

### Service layer

`src/goalflow/service/message_service.py::MessageService` is the read/write API the app uses (e.g. `get_by_message_id`, `get_llm_template_by_conversation_id`). It coordinates cache + DB so callers don't touch either directly.

> [!NOTE]
> The roadmap calls for migrating durable message storage from **MySQL to Elasticsearch**. Because access goes through `MessageService`, that migration is mostly contained to the service + `src/goalflow/model/` layer.

## Configuration

Two sources, loaded at startup (`src/goalflow/app.py::lifespan`):

### 1. `config.yaml` (non-secret)

Read by `src/goalflow/config.py::ConfigManager` into a Pydantic `Settings` model:

- `environment` — `development` / `staging` / `production`
- `logging` — level, format (includes `request_id`), file path, rotation
- `server` — host, port, workers, reload, debug, `cors_origins`

Logging is `structlog`-based; `get_logger(__name__)` returns a structured logger, and `request_id` / `trace_info` / `trace_context` are `contextvars` propagated through the request and into LangGraph via `var_child_runnable_config`.

### 2. `.env` files (secrets + endpoints)

Loaded by `src/goalflow/tool/env_loader.py::load_env()` based on `ENV`:

| `ENV` | file |
|-------|------|
| `production` | `.env_prod` |
| `uat` | `.env_uat` |
| `test` | `.env_test` |
| else | `.env` |

### Environment variable groups

The code reads env vars across several concerns (only set what your workflow uses):

| Group | Example vars |
|-------|--------------|
| MySQL | `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`, `POOL_*` |
| Redis | `REDIS_ENABLED`, `REDIS_MODEL`, `REDIS_CLUSTERS`, `REDIS_PASSWORD`, `REDIS_*` |
| LLM providers | `DASHSCOPE_KEY`, `DASHSCOPE_ENDPOINT`, `OPENAI_KEY`, `OPENAI_ENDPOINT` |
| Skills matcher | `SKILL_MATCH_PROVIDER`, `SKILL_MATCH_MODEL` |
| Tracing | `TRACE_SWITCH_ON`, `SUPPORT_TRACE_WORKFLOW_ONLY`, `SUPPORT_TRACE_ALL_NODE`, `TRACE_PLATPORM_URL`, `LANGFUSE_*` |
| Object storage | `OSS_*`, `OSS_PUBLIC_*` |
| Tools / services | `MCP_*`, `KNOWLEDGE_BASE_*`, `FINANCIAL_BASE_URL`, `IMAGE_GENERATE_BASE_URL`, `QWEN_IMAGE_*`, `NEW_API_*`, … |
| Service registry | `NACOS_SERVER_ADDR`, `NACOS_NAMESPACE`, `NACOS_GROUP`, `NACOS_USERNAME`, `NACOS_PASSWORD` |

> [!WARNING]
> Many of these currently have **hard-coded internal defaults or committed secrets** in the repo. Before open-sourcing, externalize every endpoint and rotate every key — see [security-and-open-sourcing.md](security-and-open-sourcing.md).

## The LLM factory

`src/goalflow/llm/llm.py::LLM` is the single place models are constructed (`LLM.create(provider, model, ...)`), so provider choice (Qwen/DashScope, Azure OpenAI, Qianfan, …) is centralized. The agent kit's `ModelRouter` calls into this factory via `register_llm_factory` so the SDK stays LLM-agnostic (see [agent-kit.md](agent-kit.md#harness-governance-container)).

## Observability

- **Tracing** — `src/goalflow/trace/` wraps Langfuse. Spans chain across services via `UPSTREAM_TRACE_ID_HEADER_NAME` / `UPSTREAM_SPAN_ID_HEADER_NAME` headers → `trace_context` contextvar → `RunnableConfig`. Controlled by `TRACE_SWITCH_ON`, `SUPPORT_TRACE_WORKFLOW_ONLY`, `SUPPORT_TRACE_ALL_NODE`.
- **Memory monitoring** — `src/goalflow/monitor/` profiles the long-lived singleton workflow instances and connection pools (`memory_monitor.py`, an ASGI `MemoryMonitoringMiddleware`, and diagnostic routers). A background thread runs a periodic leak check every 5 minutes.
