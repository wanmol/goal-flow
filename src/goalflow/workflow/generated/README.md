# `generated/` — transpiler output

This directory holds **workflow classes generated from Dify DSL exports** by the
transformer (`goalflow.tool.dify_transformer`). Each file defines a
`BaseWorkflow[BaseState]` subclass with `_setup_nodes` / `_setup_edges` /
variable-setup methods emitted from the visual flow.

## How files land here

By default the transformer writes to this directory:

```bash
python -m goalflow.tool.dify_transformer.wf_transformer_tool \
    --dsl path/to/my_flow.yml \
    --out my_flow_workflow.py \
    --class MyFlowWorkflow
```

See [docs/dify-transformer.md](../../../../docs/dify-transformer.md) and
[docs/tutorials.md](../../../../docs/tutorials.md) for the full walkthrough.

## What's tracked vs. generated

- `demo_chatflow.py` — a committed example (`DemoChatflow`, registered in
  `goalflow/api/auth_validator.py`). Keep it as a reference.
- Other `*.py` files you transpile are **build artifacts**. They are safe to
  regenerate and you generally should not commit them unless a specific
  workflow is meant to ship with the repo.
- `__pycache__/` is transient and ignored.

`.gitkeep` keeps the directory present in a fresh clone even before you
generate anything.
