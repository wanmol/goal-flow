[English](getting-started.md) | **简体中文**

# 快速开始

本指南带你从克隆代码库到运行起一个工作流服务。

## 1. 前置条件

- **Python 3.12**（参见 `requirements.txt`）。
- **Redis** —— 集群或单机模式。用于消息缓存、会话变量缓存以及任务停止标志。
- **MySQL** —— 持久化消息存储、HITL（人在环）审核以及会话变量。同时也作为 LangGraph checkpointer（`langgraph-checkpoint-mysql`）的后端。

## 2. 克隆代码

agent 循环 SDK（`agent_kit`）已直接内置（vendored）到 `src/agent_kit/` 中 —— 没有 git 子模块，因此一次普通的克隆即可自包含。

```bash
git clone <your-repo-url>
cd goalflow
```

## 3. 安装依赖

goalflow 采用 `src/` 布局，包含两个包：`goalflow`（框架本身）和 `agent_kit`（内置的 agent SDK）。可编辑安装（editable install）会把两者都加入你的 path。

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -e .                # installs goalflow + agent_kit and their deps
# or, without installing the package:
pip install -r requirements.txt
```

部分依赖体积较大且可选，取决于你的使用场景（OSS、MCP、文档解析）。如果你只需要核心引擎，可以精简 `requirements.txt`。

## 4. 配置环境

配置来自两处：

- **`config.yaml`** —— 非机密设置：环境名称、日志、服务的 host/port/CORS。由 `goalflow.config::ConfigManager` 加载。
- **`.env` 文件** —— 机密信息和服务端点，由 `goalflow.tool.env_loader::load_env()` 根据 `ENV` 变量加载：

  | `ENV` value | file loaded |
  |-------------|-------------|
  | `production` | `.env_prod` |
  | `uat` | `.env_uat` |
  | `test` | `.env_test` |
  | anything else / unset | `.env` |

> [!IMPORTANT]
> 当前仓库中随附的 `.env*` 文件包含真实的机密信息。**请勿复用它们。** 请根据下方模板创建你自己的文件，并且永远不要提交它们。参见 [security-and-open-sourcing.md](security-and-open-sourcing.md)。

用于启动核心引擎的最小化 `.env`：

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

代码读取的完整环境变量集合（OSS、MCP、图像生成、LLM 密钥、Langfuse 等）记录在 [storage-and-config.md](storage-and-config.md) 中，`.env.example` 中也随附了一份模板。其中大多数只有在你使用对应的工具/节点时才需要。

## 5. 注册一个工作流

工作流是继承自 `BaseWorkflow[BaseState]` 的 Python 类。请求会通过 [`src/goalflow/api/auth_validator.py`](../src/goalflow/api/auth_validator.py) 中的 API key → 工作流映射被路由到某个工作流实例：

```python
# src/goalflow/api/auth_validator.py
apikey_workflow_def_map = {
    # md5(api_key_string) : WorkflowClass
    "2999a65aa67e37253623075d60796f9a": MyWorkflow,
}
```

映射的键是通过 `Authorization: Bearer <api_key>` 请求头发送的 **API key 的 MD5 十六进制摘要**。要注册一个工作流：

1. 生成一个工作流类 —— 既可以转译一份 Dify DSL（参见 [dify-transformer.md](dify-transformer.md)），也可以手写。
2. 在 `src/goalflow/api/auth_validator.py` 中导入该类。
3. 计算 `md5(your_api_key)` 并添加对应条目。

实例采用惰性创建并按类缓存（`get_workflow`），`bind_subworkflows()` 会在创建时被调用一次。

> [!NOTE]
> 这种在代码中静态映射的方式是当前的设计。对于真正的生产部署，这会是你首先想要替换掉的东西 —— 参见[设计说明](design-notes.md#authentication--workflow-registration)了解基于配置/数据库的替代方案。

## 6. 运行服务

```bash
goalflow-server                     # console script (after pip install -e .)
# or
python start_server.py
# or
uvicorn goalflow.app:app --host 0.0.0.0 --port 8000 --reload
```

服务启动在 `http://localhost:8000`。FastAPI 的交互式文档位于 `http://localhost:8000/docs`。

启动时（`goalflow.app::lifespan`），服务会：
- 加载环境变量，
- 初始化 MySQL 连接池（`Database.init()`）和 Redis 集群（`RedisClusterManager.init_cluster()`），
- 运行一次中间件健康检查，
- 启动内存监控器以及一个周期性的泄漏检查线程。

## 7. 发送请求

流式对话（chatflow）：

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

所有端点以及请求/响应的结构参见 [api-reference.md](api-reference.md)。

## 下一步

- 理解请求生命周期 → [architecture.md](architecture.md)
- 转换你的第一个 Dify 流程 → [dify-transformer.md](dify-transformer.md)
- 学习节点库 → [nodes.md](nodes.md)
