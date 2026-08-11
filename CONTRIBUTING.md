# Contributing to goalflow

Thanks for your interest in improving goalflow! This guide covers how to set up a
dev environment, the conventions we follow, and how to get a change merged.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

goalflow uses a `src/` layout with two packages: `goalflow` (the framework) and
`agent_kit` (the vendored agent SDK).

```bash
git clone <your-fork-url>
cd goalflow

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -e .                  # installs goalflow + agent_kit and deps
cp .env.example .env              # then fill in real values (never commit .env)
```

See [docs/getting-started.md](docs/getting-started.md) for full configuration
(Redis, MySQL, LLM keys) and [docs/tutorials.md](docs/tutorials.md) for
end-to-end walkthroughs.

## Running the tests

```bash
python -m pytest test/ -q                 # framework tests
python -m pytest src/agent_kit/tests -q   # agent_kit tests (if present)

# a single file
python -m pytest test/unit_tests/test_code_node.py -q
```

Many integration demos under `test/integration_tests/` accept a `--mock` flag so
they run without live LLM credentials. Please make sure the test suite passes
before opening a pull request; CI runs the same commands.

## Coding conventions

- **Python 3.12+**, matching `requires-python` in `pyproject.toml`.
- **Comments and docstrings in English.** Keep string literals that affect
  runtime behavior (prompt templates, log/exception messages) as-is unless the
  change is specifically about them.
- **Match the surrounding code.** Follow the naming, structure, and comment
  density already present in the file you're editing.
- **Nodes** extend `BaseNode`; **workflows** extend `BaseWorkflow[BaseState]`;
  **agents** subclass `AgentBaseNode` (see [docs/agent-kit.md](docs/agent-kit.md)).
- Don't commit generated artifacts under `src/goalflow/workflow/generated/`
  unless a specific workflow is meant to ship (see that directory's README).

## Commit messages

Use short, typed messages following the existing history:

```
<type>: <imperative summary>

<optional body explaining the why>
```

Common types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`. Keep the
subject under ~70 characters and explain the reasoning in the body when it
isn't obvious.

## Pull requests

1. Fork and create a topic branch off `main`.
2. Make focused changes with tests where it makes sense.
3. Ensure `pytest` passes and no secrets or `.env*` files are staged.
4. Open a PR describing **what** changed and **why**, linking any related issue.

Before touching anything that could ship publicly, skim
[docs/security-and-open-sourcing.md](docs/security-and-open-sourcing.md) — never
add real credentials, internal hostnames, or IPs to tracked files.

## Reporting bugs and requesting features

Use the issue templates under [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/).
For anything security-sensitive, do **not** open a public issue — follow the
disclosure guidance in the security checklist instead.
