[English](security-and-open-sourcing.md) | **简体中文**

# 安全与开源检查清单

> [!CAUTION]
> **在完成"发布前必须修复"中的各项之前，请勿将本仓库推送到任何公开托管平台。** `.env*` 文件已不再被跟踪，但真实的生产环境凭证仍存在于 git 历史中。将仓库设为公开——甚至只是推送到他人可读的私有远程——都会暴露这些凭证，直到历史被彻底清除且每个密钥都完成轮换为止。

## 发布前必须修复

### 1. 从 git 历史中清除已提交的密钥

`.env*` 文件**已不再被跟踪**——它们已从工作区中移除，并以一个 `.env.example` 模板取而代之。但它们仍在 **git 历史中**包含真实密钥，因此危险尚未解除：

| File | Contains |
|------|----------|
| `.env` | MySQL 主机/用户名/密码、Redis 集群主机/密码、`DASHSCOPE_KEY`、`OPENAI_KEY`（Azure）、`OSS_*` 密钥、`LANGFUSE_*` 密钥、MCP/知识库/图像 API 密钥、内部服务 URL |
| `.env_prod` | 生产环境对应值 |
| `.env_test` | 测试环境对应值 |
| `.env_uat` | UAT 环境对应值 |
| `deployment.yaml` | 部署配置（需检查是否内嵌了密钥） |

仅仅取消跟踪这些文件是**不够的**——它们仍留在历史中。剩余步骤：

1. **立即轮换每一个凭证。** 假定上述全部凭证均已泄露：数据库密码、Redis 密码、DashScope 密钥、Azure OpenAI 密钥、OSS 访问密钥、Langfuse 密钥、MCP/图像/new-api 密钥。无论清理与否都要轮换，因为它们一直躺在历史里。
2. 在首次公开推送之前，使用 `git filter-repo`（首选）或 BFG **清除历史**：
   ```bash
   pip install git-filter-repo
   git filter-repo --path .env --path .env_prod --path .env_test --path .env_uat --invert-paths
   ```
   然后强制推送到一个**全新的**远程（不要重用历史中已经含有这些密钥的远程）。

   > 这会重写历史——请与任何持有克隆副本的人协调。

### 2. 修复 `.gitignore` —— 已完成

`.gitignore` 现在会忽略 `.env`、`.env.*` 和 `.env_*`（并带有一个 `!.env.example` 例外），同时也忽略 `*.log`，且 `app.log` 已不再被跟踪。无需再对 `.gitignore` 做进一步处理；剩余的风险是第 1 项中的历史清除。

### 3. 外部化硬编码的内部端点

`src/goalflow/dify_parser/dify_dsl_parser.py` 会重写一组硬编码的内部主机（rerank、知识库索引器、hologres、图像生成、时间服务、ES），而 `.env` 中固定了许多内部 IP（`10.3.x.x`、`172.26.x.x`）和内部域名。发布前：

- 用环境变量 + 有文档说明的默认值替换硬编码主机。
- 从已提交的文件和示例中清除内部 IP/域名。

### 4. 提供 `.env.example` —— 已完成

现已提供一个带**占位符**值的 `.env.example` 模板（最小集合见 [getting-started.md](getting-started.md#4-configure-environment)），让用户知道需要填写什么，而不含任何真实值。随着新增环境变量，请保持其同步，并确保没有真实值重新混入其中。

### 5. 添加 LICENSE —— 已完成

现已存在一个 `LICENSE` 文件（MIT）。`agent_kit` SDK 不再是子模块——它已被内联（vendored）进 `src/agent_kit/` 并重新以 MIT 许可，因此不再有需要访问的外部远程，其许可也是兼容的。

## 发布前应当修复

- **API 密钥认证基于 MD5**（`src/goalflow/api/auth_validator.py`）。MD5 不适合用于密钥哈希。如果密钥被当作机密对待，应使用强哈希的常量时间比较（或一个正规的令牌存储）。至少要在文档中说明该映射只是一个演示机制。见 [design-notes.md](design-notes.md#authentication--workflow-registration)。
- **CORS 完全开放**（`allow_origins="*"` 且 `allow_credentials=True`）。这一组合按 CORS 规范是非法的，也不安全；任何真实部署都应限制来源。
- **`CodeNode` 通过 `exec` 执行模型/DSL 提供的 Python 代码**。解析器中的 `safe_check()` AST 防护目前处于禁用/TODO 状态。请仅将生成的代码视为可信输入，并在接受不可信 DSL 之前重新启用/加强沙箱化。
- **移除不应公开的领域专有密钥/逻辑**（金融服务 URL、会员权益端点等），或将它们清晰地分离到一个可选模块中。

## 锦上添花

- 一份 `CONTRIBUTING.md`、issue 模板和行为准则。
- 运行现有测试（`test/`、`src/agent_kit/tests/`）的 CI。
- 如果你保留多环境模式，为每个环境提供一份 `.env.example`（`.env.prod.example`、……）。
- 如果 `app.log` 历史中包含请求负载，对其进行脱敏。

## 发布前快速审计命令

```bash
# what secrets/config are tracked?
git ls-files | grep -E '\.env|\.pem|\.key|deployment\.yaml|\.log$'

# scan history for a known secret fragment (replace with a rotated value's prefix)
git log -p -S 'sk-' -- . | head

# find hard-coded internal IPs
grep -rEn '10\.3\.|172\.26\.|\.aliyuncs\.com' --include='*.py' --include='*.env*' .
```
