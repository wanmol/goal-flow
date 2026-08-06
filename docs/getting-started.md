**English** | [简体中文](getting-started.zh-CN.md)

# Getting Started

This guide takes you from a clone to a running workflow server.

## 1. Prerequisites

- **Python 3.12** (see `requirements.txt`).
- **Redis** — cluster or standalone. Used for message caching, conversation-variable caching, and task stop flags.
- **MySQL** — durable message storage, HITL reviews, and conversation variables. Also backs the LangGraph checkpointer (`langgraph-checkpoint-mysql`).

## 2. Clone

The agent-loop SDK (`agent_kit`) is vendored directly into `src/agent_kit/` — there are no git submodules, so a plain clone is self-contained.

```bash
git clone <your-repo-url>
cd goalflow
```

## 3. Install dependencies

goalflow uses a `src/` layout with two packages: `goalflow` (the framework) and `agent_kit` (the vendored agent SDK). An editable install puts both on your path.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -e .                # installs goalflow + agent_kit and their deps
# or, without installing the package:
pip install -r requirements.txt
```

Some dependencies are heavy and optional depending on what you use (OSS, MCP, document parsing). If you only need the core engine you can trim `requirements.txt`.

## 4. Configure environment

Configuration comes from two places:

- **`config.yaml`** — non-secret settings: environment name, logging, server host/port/CORS. Loaded by `goalflow.config::ConfigManager`.
- **`.env` files** — secrets and service endpoints, loaded by `goalflow.tool.env_loader::load_env()` based on the `ENV` variable:

  | `ENV` value | file loaded |
  |-------------|-------------|
  | `production` | `.env_prod` |
  | `uat` | `.env_uat` |
  | `test` | `.env_test` |
  | anything else / unset | `.env` |

> [!IMPORTANT]
> The repository currently ships `.env*` files containing real secrets. **Do not reuse them.** Create your own from the template below and never commit them. See [security-and-open-sourcing.md](security-and-open-sourcing.md).

Minimal `.env` to boot the core engine:

```dotenv
FASTAPI_ENV=development

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DB=workflow
POOL_SIZE=20
MAX_OVERFLOW=20
POOL_RECYCLE=600
POOL_PRE_PING=True
POOL_TIMEOUT=30

# Redis (set REDIS_ENABLED=False to run without Redis)
REDIS_ENABLED=True
REDIS_MODEL=standalone           # or: cluster
REDIS_CLUSTERS=localhost:6379
REDIS_PASSWORD=
REDIS_USERNAME=default
REDIS_DB=0
REDIS_POOL_SIZE=50
REDIS_POOL_TIMEOUT=10
REDIS_SOCKET_TIMEOUT=10
REDIS_CONNECT_TIMEOUT=10
CACHE_DEFAULT_TIMEOUT=300
MESSAGES_PER_PAGE=25

# LLM providers (use whichever your workflow needs)
DASHSCOPE_KEY=sk-...
DASHSCOPE_ENDPOINT=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_KEY=...
OPENAI_ENDPOINT=https://your-azure-openai.openai.azure.com/

# Tracing (optional — set TRACE_SWITCH_ON=0 to disable)
TRACE_SWITCH_ON=0
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_BASE_URL=
```

The full set of environment variables the code reads (OSS, MCP, image generation, LLM keys, Langfuse, etc.) is documented in [storage-and-config.md](storage-and-config.md), and a template ships in `.env.example`. Most are only needed if you use the corresponding tool/node.

## 5. Register a workflow

Workflows are Python classes extending `BaseWorkflow[BaseState]`. A request is routed to a workflow instance by an API-key → workflow mapping in [`src/goalflow/api/auth_validator.py`](../src/goalflow/api/auth_validator.py):

```python
# src/goalflow/api/auth_validator.py
apikey_workflow_def_map = {
    # md5(api_key_string) : WorkflowClass
    "2999a65aa67e37253623075d60796f9a": MyWorkflow,
}
```

The map key is the **MD5 hex digest of the API key** sent in the `Authorization: Bearer <api_key>` header. To register a workflow:

1. Generate a workflow class — either transpile a Dify DSL (see [dify-transformer.md](dify-transformer.md)) or hand-write one.
2. Import the class in `src/goalflow/api/auth_validator.py`.
3. Compute `md5(your_api_key)` and add the entry.

Instances are created lazily and cached per class (`get_workflow`), and `bind_subworkflows()` is called once at creation.

> [!NOTE]
> This static in-code mapping is the current design. It's the first thing you'll want to replace for a real deployment — see the [design notes](design-notes.md#authentication--workflow-registration) for a config/DB-driven alternative.

## 6. Run the server

```bash
goalflow-server                     # console script (after pip install -e .)
# or
python start_server.py
# or
uvicorn goalflow.app:app --host 0.0.0.0 --port 8000 --reload
```

The service starts on `http://localhost:8000`. FastAPI's interactive docs are at `http://localhost:8000/docs`.

On startup (`goalflow.app::lifespan`) the server:
- loads env vars,
- initializes the MySQL pool (`Database.init()`) and Redis cluster (`RedisClusterManager.init_cluster()`),
- runs a middleware health check,
- starts the memory monitor and a periodic leak-check thread.

## 7. Send a request

Streaming chat (chatflow):

```bash
curl -N http://localhost:8000/v1/chat-messages \
  -H "Authorization: Bearer <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{
        "query": "hello",
        "user": "user-123",
        "conversation_id": null,
        "response_mode": "streaming",
        "inputs": {}
      }'
```

See [api-reference.md](api-reference.md) for all endpoints and the request/response shapes.

## Next steps

- Understand the request lifecycle → [architecture.md](architecture.md)
- Convert your first Dify flow → [dify-transformer.md](dify-transformer.md)
- Learn the node library → [nodes.md](nodes.md)
