**English** | [简体中文](design-notes.zh-CN.md)

# Design Notes & Improvement Suggestions

An honest assessment of the framework's design, with concrete, actionable suggestions. The framework's *core ideas are strong* — a node library, a visual-tool-to-code transpiler, a pluggable protocol layer, and a graph+loop agent model. The suggestions below are about polishing it for a general open-source audience and hardening it for production.

Nothing here is required to run the code; these are recommendations.

## Security (see the dedicated checklist)

The highest-priority items — committed secrets, `.gitignore` gaps, hard-coded internal endpoints, MD5 auth, open CORS, `exec` in `CodeNode`, missing LICENSE — are in [security-and-open-sourcing.md](security-and-open-sourcing.md). Do those first.

## Authentication & workflow registration

**Current:** `src/goalflow/api/auth_validator.py` maps `md5(api_key) → WorkflowClass` in an in-code dict, and each class is instantiated as a process-wide singleton.

**Issues:** MD5 for secret comparison; recompiling to add a workflow; no per-key metadata (rate limits, ownership, scopes); singletons make per-request isolation subtle.

**Suggestion:** Move the mapping to config or a DB table (`api_key_hash`, `workflow_ref`, `enabled`, `owner`, …), hash keys with a strong algorithm and constant-time compare, and load workflow classes by dotted path. Keep the in-code map as a documented "quickstart" fallback.

## Domain fields in state

**Current:** `BaseState` mixes generic system/routing/variable fields with a large block of **financial-report** domain fields (`rewritten_query`, `question_type`, `core_view`, `*_period_analysis`, …).

**Issue:** The generic base carries baggage irrelevant to most users; it leaks the framework's origin.

**Suggestion:** Keep `BaseState` minimal (system + routing + the four variable pools + trace + HITL + sub-workflow bridging). Put domain fields in a subclass (`FinancialReportState(BaseState)`) that specific workflows parameterize `BaseWorkflow[FinancialReportState]` with. LangGraph already supports per-graph state schemas, so this is low-risk.

## Dify parser mutates input

**Current:** `DifyDslParser.parse()` opens the DSL file `r+`, applies a series of `str.replace()` host rewrites, and **writes the file back in place** before parsing.

**Issues:** Destructive to the user's export; embeds site-specific hostnames; makes the parse non-idempotent and hard to test.

**Suggestion:** Read-only parse. Do host substitution on the in-memory string (or better, keep DSL values as-is and resolve endpoints from env at *runtime*, not parse time). If rewriting is desired, write to a new file and log the mapping. Make the substitution table configurable rather than hard-coded.

## Transformer CLI

**Current:** `src/goalflow/tool/dify_transformer/wf_transformer_tool.py::main()` hard-codes the input path, output filename, and class name, with dozens of commented-out prior invocations.

**Suggestion:** Make it a real CLI:

```bash
python -m goalflow.tool.dify_transformer.wf_transformer_tool \
    --dsl path/to/flow.yml \
    --out my_flow_workflow.py \
    --class MyFlowWorkflow
```

Use `argparse`, validate paths, and drop the commented history (git remembers it).

## Data adapter contract

**Current:** `AbstractDataAdapter` declares `generate` twice (streaming + blocking); Python keeps only the second, so the abstract contract is effectively "implement one `generate`." Concrete `OpenAIDataAdapter` actually exposes `generate` (stream) + `execute` (blocking), and `src/goalflow/app.py` calls `.execute()`.

**Suggestion:** Make the base class match reality — two distinctly named abstract methods:

```python
class AbstractDataAdapter(ABC):
    @abstractmethod
    def generate(self, generator: Iterator[str]) -> Iterator[str]: ...
    @abstractmethod
    def execute(self, data: ChatCompletionBlockingResponse) -> dict: ...
```

Also add a tiny "Dify adapter" class even if it's the identity/default, so all protocols are represented uniformly and discoverable.

## Naming, typos, and hygiene

- **Resolved:** The `WorkflowError` / `StateValidationError` exception handlers previously returned a plain dict with a `status_code` key, which Starlette tried to invoke as an ASGI app so they never produced a 400. They now return `JSONResponse(status_code=400, content=...)`.
- `_get_status_code_by_error_msg` string-matches `"status_code: 4"` to decide 403 — fragile; carry a real status on the exception type instead.
- `src/goalflow/workflow/generated/` is created at generation time and has no committed contents; add a `.gitkeep` and a short README so the directory's purpose is clear.

## Agent-kit integration

**Resolved:** `agent_kit` was previously a git submodule pointing at an internal Aliyun Codeup URL, which external users couldn't clone if the remote wasn't public and which was awkward for dependency management and versioning. It has since been **vendored** directly into the repo at `src/agent_kit/` (relicensed MIT) under a clear boundary, so there are no submodules to fetch.

**Remaining option:** Publishing `agent_kit` to a public host / PyPI and depending on a pinned version is still a possible future step if independent versioning becomes valuable.

## Observability & ops

- The memory-monitor stack (`src/goalflow/monitor/`) is elaborate (multiple analyzers, a background leak thread, ASGI middleware, diagnostic routes). For an open-source default, consider making it opt-in via config so the framework doesn't spawn threads and instrument every request out of the box.
- The periodic leak check `print()`s alerts; route these through the structured logger instead.

## Testing & docs

- There's a good test base (`test/unit_tests/`, `test/integration_tests/`, `src/agent_kit/tests/`). Wire it into CI and add a "how to run tests" section.
- **Added:** Three end-to-end tutorials now live in [tutorials.md](tutorials.md): (1) transpile a tiny Dify flow and hit it, (2) build an `AgentBaseNode`, (3) implement a custom `DataAdapter`. Tutorials 2 and 3 flag that those layers are defined but not yet wired into the default request path, so the reader knows where they're extending the framework.

## What's already good (keep it)

- The **node lifecycle** wrapper (uniform tracing/logging/fan-in/error-strategy) is clean and consistent.
- The **branch-aware streaming** (only stream tokens from nodes that provably reach an answer/end) is a genuinely nice touch that avoids leaking untaken-branch output.
- The **parser/visitor/generator** separation makes supporting new visual tools tractable.
- The **harness + middleware** design in the agent kit is a solid, testable governance model.
- **Checkpointer-backed HITL** with `resume(Command(resume=...))` is the right LangGraph-native approach.
