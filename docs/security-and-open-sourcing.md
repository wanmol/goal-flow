**English** | [简体中文](security-and-open-sourcing.zh-CN.md)

# Security & Open-Sourcing Checklist

> [!CAUTION]
> **Do not push this repository to a public host until the items in "Must fix before publishing" are done.** The `.env*` files are no longer tracked, but live production credentials still exist in git history. Making the repo public — or even pushing to a private remote that others can read — exposes them until the history is scrubbed and every key is rotated.

## Must fix before publishing

### 1. Purge committed secrets from git history

The `.env*` files are **no longer tracked** — they've been removed from the working tree and a `.env.example` template ships in their place. But they still contain real secrets **in git history**, so the danger is not over:

| File | Contains |
|------|----------|
| `.env` | MySQL host/user/password, Redis cluster host/password, `DASHSCOPE_KEY`, `OPENAI_KEY` (Azure), `OSS_*` keys, `LANGFUSE_*` keys, MCP/knowledge/image API keys, internal service URLs |
| `.env_prod` | production equivalents |
| `.env_test` | test equivalents |
| `.env_uat` | UAT equivalents |
| `deployment.yaml` | deployment config (review for embedded secrets) |

Untracking the files is **not enough** — they remain in history. Remaining steps:

1. **Rotate every credential now.** Assume all of the above are compromised: database passwords, Redis password, DashScope key, Azure OpenAI key, OSS access keys, Langfuse keys, MCP/image/new-api keys. Rotate them regardless of the cleanup, because they've been sitting in history.
2. **Scrub history** before the first public push, using `git filter-repo` (preferred) or BFG:
   ```bash
   pip install git-filter-repo
   git filter-repo --path .env --path .env_prod --path .env_test --path .env_uat --invert-paths
   ```
   Then force-push to a **fresh** remote (don't reuse a remote that already has the secrets in its history).

   > This rewrites history — coordinate with anyone who has a clone.

### 2. Fix `.gitignore` — DONE

The `.gitignore` now ignores `.env`, `.env.*`, and `.env_*` (with a `!.env.example` exception) alongside `*.log`, and `app.log` is no longer tracked. No further `.gitignore` work is required; the remaining risk is the history scrub in item 1.

### 3. Externalize hard-coded internal endpoints

`src/goalflow/dify_parser/dify_dsl_parser.py` rewrites a list of hard-coded internal hosts (rerank, knowledge indexer, hologres, image-gen, time service, ES) and `.env` pins many internal IPs (`10.3.x.x`, `172.26.x.x`) and internal domains. Before publishing:

- Replace hard-coded hosts with env vars + documented defaults.
- Scrub internal IPs/domains from committed files and examples.

### 4. Provide a `.env.example` — DONE

A `.env.example` template with **placeholder** values now ships (see [getting-started.md](getting-started.md#4-configure-environment) for the minimal set) so users know what to fill in, without any real values. Keep it in sync as new env vars are added, and make sure no real values slip back in.

### 5. Add a LICENSE — DONE

A `LICENSE` file (MIT) now exists. The `agent_kit` SDK is no longer a submodule — it has been vendored into `src/agent_kit/` and relicensed MIT, so there's no external remote to reach and its license is compatible.

## Should fix before publishing

- **API-key auth is MD5-based** (`src/goalflow/api/auth_validator.py`). MD5 is unsuitable for secret hashing. If keys are treated as secrets, use a constant-time compare of a strong hash (or a proper token store). At minimum, document that the map is a demo mechanism. See [design-notes.md](design-notes.md#authentication--workflow-registration).
- **CORS is fully open** (`allow_origins="*"` with `allow_credentials=True`). This combination is invalid per the CORS spec and unsafe; restrict origins for any real deployment.
- **`CodeNode` executes model/DSL-provided Python** via `exec`. The `safe_check()` AST guard in the parser is currently disabled/TODO. Treat generated code as trusted-input only, and re-enable/strengthen sandboxing before accepting untrusted DSLs.
- **Remove domain-specific secrets/logic** that shouldn't be public (financial service URLs, member-rights endpoints, etc.), or clearly separate them into an optional module.

## Nice to have

- A `CONTRIBUTING.md`, issue templates, and a code of conduct.
- CI that runs the existing tests (`test/`, `src/agent_kit/tests/`).
- A `.env.example` per environment (`.env.prod.example`, …) if you keep the multi-env pattern.
- Redact `app.log` history if it contains request payloads.

## Quick pre-publish audit commands

```bash
# what secrets/config are tracked?
git ls-files | grep -E '\.env|\.pem|\.key|deployment\.yaml|\.log$'

# scan history for a known secret fragment (replace with a rotated value's prefix)
git log -p -S 'sk-' -- . | head

# find hard-coded internal IPs
grep -rEn '10\.3\.|172\.26\.|\.aliyuncs\.com' --include='*.py' --include='*.env*' .
```
