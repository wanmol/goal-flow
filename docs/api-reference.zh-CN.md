[English](api-reference.md) | **简体中文**

# API 参考

所有端点都定义在 [`app.py`](../src/goalflow/app.py) 以及 [`api/`](../src/goalflow/api/) 目录下的路由中。需要鉴权的工作流端点期望携带：

```
Authorization: Bearer <api_key>
```

该密钥经过 MD5 哈希后，在 `apikey_workflow_def_map` 中查找以解析出目标工作流实例（参见 [getting-started.md](getting-started.md#5-register-a-workflow)）。

可选的追踪请求头用于传播分布式追踪：一个上游 request-id 请求头，以及上游的 `trace_id` / `span_id` 请求头（对应常量 `WF_REQUEST_ID_HEADER_NAME`、`UPSTREAM_TRACE_ID_HEADER_NAME`、`UPSTREAM_SPAN_ID_HEADER_NAME`）。

## 对话与工作流

### `POST /v1/chat-messages`

运行一个 **chatflow**（工作流类型必须为 `chatflow`）。支持流式和阻塞两种模式。

请求体（`WorkflowInput`）：

| 字段 | 类型 | 默认值 | 说明 |
|-------|------|---------|-------|
| `query` | string | `""` | 用户消息 |
| `user` | string | **必填** | 用户 id |
| `conversation_id` | string? | `null` | 省略以开启新会话 |
| `response_mode` | string | `"streaming"` | `streaming` 或 `blocking` |
| `scene_type` | string? | `null` | |
| `sys_app_id` | string | `"aira-workflow"` | |
| `sys_workflow_id` | string | （默认 id） | |
| `files` | list? | `null` | 上传的文件 |
| `inputs` | object | `{}` | 工作流输入变量（例如 `use_end_stream`） |

- **流式** → `text/event-stream`（SSE）。响应头 `X-Workflow-Run-ID` 携带运行 id。帧的格式遵循当前激活的 [数据适配器](protocols-and-adapters.md)；默认为 Dify chunk 结构（`chunk_id`、`type`、`data`、`timestamp`），生命周期类型包括 `workflow_started` / `node_finished` / `text_chunk` / `error` / `done`。
- **阻塞** → 单个 JSON 响应。

### `POST /v1/chat-messages/{task_id}/stop`

为运行中的任务设置 Redis 停止标志，使其流式输出终止。返回 `{"success": true, ...}`。

### `POST /v1/workflows/run`

运行一个 **workflow** 类型（非对话）。通过 `WorkflowGenerateService` 使用相同的流式/阻塞模型。

### `POST /v1/chat/completions`

**OpenAI 兼容** 的对话端点（为 LLM 应用备案/合规而添加）。接受 `ChatCompletionRequest`；响应使用 `OpenAIDataAdapter`（`chat.completion.chunk` 流式，或一个 `chat.completion` 对象）。使得 OpenAI-API 客户端能够驱动你的工作流。参见 [protocols-and-adapters.md](protocols-and-adapters.md#the-included-alternative-openai-compatible)。

### `POST /v1/images/generations`

生成一张图片（`ImageGenerationRequest` → `ImageGenerationResponse`）。下载生成的图片，添加水印，上传至 OSS，并返回 CDN URL。需要图片生成相关配置和 `OSS_PUBLIC_*` 环境配置。

## 推荐问题

### `POST /v1/messages/{message_id}/suggested`

根据最近的会话历史生成后续问题建议。请求体可包含 `tpl_id` 用于选择提示词模板（`suggest_q_tpl_map`）。查询参数 `user` 为必填。返回 `{"result": "success", "data": [...]}`。

### `GET /v1/messages/{message_id}/suggested`

用途相同，为 GET 变体，使用默认提示词模板。查询参数 `user` 为必填。

## 人在环（Human-in-the-Loop）—— `src/goalflow/api/hitl_api.py`

路由前缀 **`/api/v1/hitl`**。参见 [streaming-and-hitl.md](streaming-and-hitl.md#human-in-the-loop-hitl)。

| 方法与路径 | 用途 |
|---------------|---------|
| `GET /reviews/{review_id}` | 获取某条审核的详情 |
| `GET /workflows/{workflow_run_id}/reviews` | 列出某次运行的所有审核 |
| `POST /reviews/approve` | 批准审核（恢复工作流） |
| `POST /reviews/modify` | 带修改地批准 |
| `POST /reviews/reject` | 驳回审核 |
| `POST /workflows/{workflow_run_id}/resume` | 手动恢复一个暂停的工作流 |
| `GET /health` | HITL 健康检查 |

## 报告 —— `src/goalflow/api/report_api.py`

路由前缀 **`/v1/reports`**。由 `src/goalflow/service/report_service.py` 支撑。

| 方法与路径 | 用途 |
|---------------|---------|
| `POST /list` | 列出报告 |
| `POST /detail` | 获取某份报告的详情 |
| `POST /versions` | 列出某份报告的版本 |

## 健康与诊断

| 方法与路径 | 用途 |
|---------------|---------|
| `GET /` | 根路径 / 存活探测 |
| `GET /health` | 健康检查 |
| `GET /middle_health` | 中间件（Redis/MySQL）健康检查 |
| `GET /memory-intensive` | 内存监控器的测试端点 |
| （内存路由） | 从 `src/goalflow/monitor/memory_routes*.py` 注册的诊断路由 |

## 关于当前 API 表面的说明

- 有两个都名为 `stream_workflow` 的函数分别装饰了 `/v1/chat-messages` 和 `/v1/chat/completions`；这种遮蔽对 FastAPI 无害（每个装饰器都独立注册），但会让阅读代码的人感到困惑。
- `WorkflowError` / `StateValidationError` 的异常处理器返回的是带有 `status_code` 字段的字典，而不是设置 HTTP 状态码；建议改为返回一个规范的 `JSONResponse`。参见 [design-notes.md](design-notes.md)。
