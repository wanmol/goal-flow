[English](storage-and-config.md) | **简体中文**

# 存储与配置

本页介绍多个节点共享的图 **状态（state）**、基于 **Redis + MySQL** 的持久化设计，以及 **配置 / 环境变量** 的加载方式。

## 状态（State）

`BaseState`（`src/goalflow/state/__init__.py`）是每个节点读写的 `TypedDict`；`GenericState = TypeVar(bound=BaseState, covariant=True)` 是 `BaseNode`/`BaseWorkflow` 使用的泛型。

### 系统字段

在 `src/goalflow/app.py::prepare_initial_state` 中根据请求初始化：

`sys_query`、`sys_user_id`、`sys_app_id`、`sys_workflow_id`、`sys_workflow_run_id`、`sys_conversation_id`、`sys_dialogue_count`、`sys_files`、`sys_scene_type`、`sys_use_end_stream`、`sys_current_date`、`sys_current_datetime`。

### 路由 / 运行时字段

`node_id`、`source_handle`、`step`、`iteration_round`、`request_id`、`rt_thread_id`（检查点键）。

### 变量池

共四个变量池，外加最终输出，每一个都带有一个 **reducer**，用于控制并发写入如何合并：

| 字段 | Reducer | 说明 |
|-------|---------|-------|
| `input_variables` | `update_vars`（浅合并） | 请求输入 + 起始节点变量 |
| `output_variables` | `update_vars` | 各节点输出，以节点 id 为前缀 |
| `conversation_variables` | `update_vars` | 从数据库加载 / 持久化到数据库 |
| `environment_variables` | `update_vars` | 来自 DSL |
| `outputs` | — | 工作流最终输出（来自 `end`） |
| `node_span_ids` | `deep_merge_vars`（递归） | 追踪 span；深度合并，使并行节点不会覆盖嵌套的 `upstreams` |

Reducer 定义在 `src/goalflow/state/` 中：`persist_value`（当某个节点写入 `None` 时保留检查点中的值）、`update_vars`（浅合并）、`deep_merge_vars`（递归）。大多数标量路由字段使用 LangGraph 的 `AnyValue`/`LastValue` 通道。

### 子工作流与 HITL 字段

`_sub_workflow_caller_node_id` / `_sub_workflow_caller_span_id` 用于把父图桥接到绑定的子工作流。`hitl_*` 字段承载人在环审核状态。

> [!NOTE]
> `BaseState` 还携带一大块面向财报分析领域的 **专有字段**（`rewritten_query`、`question_type`、`classification_result`、`core_view`、`*_period_analysis` 等）。这些是框架起源遗留的产物，为了得到一个干净的开源内核，应将它们从通用基类中解耦——参见 [design-notes.md](design-notes.md#domain-fields-in-state)。

## 会话持久化：Redis + MySQL

该设计将 **热数据** 与 **持久数据** 分开存储：

```
        write path
request ─────────────► Redis (fast)  ──► MySQL (durable)
                       cache/            db/
```

### Redis（`src/goalflow/cache/`）

- `redis_manager.py::RedisClusterManager` —— 连接生命周期（`init_cluster()` / `close()`），支持集群和单机模式（`REDIS_MODEL`）。可通过 `REDIS_ENABLED` 开关整个存储层。
- `message_cache.py` —— 热消息缓存（最近若干轮对话），TTL 由 `CACHE_DEFAULT_TIMEOUT` 控制。
- `workflow_conversation_variables_cache.py` —— 会话变量缓存。
- `base_cache.py` —— 通用缓存辅助函数。
- 同时存储用于流式取消的 **任务停止标志**（`generate_task_stopped:<id>`）。

### MySQL 模型（`src/goalflow/model/`）

SQLAlchemy 模型（连接池化引擎位于 `src/goalflow/infra/`）：

- `message.py` —— 持久化的会话消息。
- `workflow_conversation_variables.py` —— 持久化的会话变量。
- `hitl_review.py` —— 人在环审核记录。
- MySQL 还作为 **LangGraph 检查点存储**（`langgraph-checkpoint-mysql`）的后端，用于流式的停止/恢复和 HITL（参见 [streaming-and-hitl.md](streaming-and-hitl.md#checkpointing)）。

### 基础设施 / 连接层（`src/goalflow/infra/`）

底层 MySQL/Redis 连接能力，由模型层和缓存层共享：

- `database.py::Database` —— 连接池生命周期（`init()` / `close()`），由 `POOL_SIZE`、`MAX_OVERFLOW`、`POOL_RECYCLE`、`POOL_PRE_PING`、`POOL_TIMEOUT` 决定规模；`Config` 持有 MySQL + Redis 环境配置。
- `redis_manager.py::RedisClusterManager` —— Redis 集群客户端 + `redis_client` 单例。
- `base_cache.py` —— 通用缓存辅助函数。
- `connection_wrapper.py` / `checkpointer_manager.py` —— 池化连接 + 用于流式/HITL 的 LangGraph 检查点存储。

### 服务层

`src/goalflow/service/message_service.py::MessageService` 是应用使用的读写 API（例如 `get_by_message_id`、`get_llm_template_by_conversation_id`）。它统一协调缓存 + 数据库，调用方无需直接接触任何一方。

> [!NOTE]
> 路线图计划将持久化消息存储从 **MySQL 迁移到 Elasticsearch**。由于访问都经过 `MessageService`，这次迁移基本可以限定在服务层 + `src/goalflow/model/` 层内完成。

## 配置

启动时加载两个来源（`src/goalflow/app.py::lifespan`）：

### 1. `config.yaml`（非机密）

由 `src/goalflow/config.py::ConfigManager` 读取到一个 Pydantic `Settings` 模型中：

- `environment` —— `development` / `staging` / `production`
- `logging` —— 级别、格式（包含 `request_id`）、文件路径、轮转
- `server` —— host、port、workers、reload、debug、`cors_origins`

日志基于 `structlog`；`get_logger(__name__)` 返回一个结构化日志器，`request_id` / `trace_info` / `trace_context` 是 `contextvars`，会在请求链路中传播，并通过 `var_child_runnable_config` 传入 LangGraph。

### 2. `.env` 文件（机密 + 端点）

由 `src/goalflow/tool/env_loader.py::load_env()` 根据 `ENV` 加载：

| `ENV` | 文件 |
|-------|------|
| `production` | `.env_prod` |
| `uat` | `.env_uat` |
| `test` | `.env_test` |
| 其他 | `.env` |

### 环境变量分组

代码在多个方面读取环境变量（只需设置你的工作流实际用到的）：

| 分组 | 示例变量 |
|-------|--------------|
| MySQL | `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DB`、`POOL_*` |
| Redis | `REDIS_ENABLED`、`REDIS_MODEL`、`REDIS_CLUSTERS`、`REDIS_PASSWORD`、`REDIS_*` |
| LLM 提供方 | `DASHSCOPE_KEY`、`DASHSCOPE_ENDPOINT`、`OPENAI_KEY`、`OPENAI_ENDPOINT` |
| 技能匹配器 | `SKILL_MATCH_PROVIDER`、`SKILL_MATCH_MODEL` |
| 追踪 | `TRACE_SWITCH_ON`、`SUPPORT_TRACE_WORKFLOW_ONLY`、`SUPPORT_TRACE_ALL_NODE`、`TRACE_PLATPORM_URL`、`LANGFUSE_*` |
| 对象存储 | `OSS_*`、`OSS_PUBLIC_*` |
| 工具 / 服务 | `MCP_*`、`KNOWLEDGE_BASE_*`、`FINANCIAL_BASE_URL`、`IMAGE_GENERATE_BASE_URL`、`QWEN_IMAGE_*`、`NEW_API_*` 等 |
| 服务注册中心 | `NACOS_SERVER_ADDR`、`NACOS_NAMESPACE`、`NACOS_GROUP`、`NACOS_USERNAME`、`NACOS_PASSWORD` |

> [!WARNING]
> 其中许多变量目前在仓库中带有 **硬编码的内部默认值或已提交的机密信息**。在开源之前，请将每个端点外部化，并轮换每一个密钥——参见 [security-and-open-sourcing.md](security-and-open-sourcing.md)。

## LLM 工厂

`src/goalflow/llm/llm.py::LLM` 是构造模型的唯一入口（`LLM.create(provider, model, ...)`），因此提供方的选择（Qwen/DashScope、Azure OpenAI、Qianfan 等）被集中管理。agent kit 的 `ModelRouter` 通过 `register_llm_factory` 调用该工厂，从而使 SDK 保持与具体 LLM 无关（参见 [agent-kit.md](agent-kit.md#harness-governance-container)）。

## 可观测性

- **追踪（Tracing）** —— `src/goalflow/trace/` 封装了 Langfuse。span 通过 `UPSTREAM_TRACE_ID_HEADER_NAME` / `UPSTREAM_SPAN_ID_HEADER_NAME` 请求头 → `trace_context` contextvar → `RunnableConfig` 在服务间串联。由 `TRACE_SWITCH_ON`、`SUPPORT_TRACE_WORKFLOW_ONLY`、`SUPPORT_TRACE_ALL_NODE` 控制。
- **内存监控（Memory monitoring）** —— `src/goalflow/monitor/` 对长期存活的单例工作流实例和连接池进行分析（`memory_monitor.py`、一个 ASGI `MemoryMonitoringMiddleware`，以及若干诊断路由）。一个后台线程每 5 分钟执行一次周期性的泄漏检查。
