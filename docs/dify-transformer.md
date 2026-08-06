**English** | [简体中文](dify-transformer.zh-CN.md)

# Dify Transformer (DSL → runnable workflow)

The transformer converts a **Dify DSL export** (`.yml`) into a **runnable LangGraph workflow** — a Python file defining a `BaseWorkflow` subclass. You design the flow visually in Dify, export it, transpile it, and run it on this framework's engine. No dependency on Dify's runtime.

## Why this exists

LangGraph has no visual designer. Dify has an excellent one but locks you into its runtime. This transformer bridges the two: use Dify (or, in future, other visual builders) for rapid design and validation, then generate code you own and can version-control, diff, and extend.

## The two-stage pipeline

```
Dify DSL (.yml)
     │
     ▼
[1] src/goalflow/dify_parser/  ──►  internal graph model (DifyDslDefinition / DifyWorkflow)
     │
     ▼
[2] src/goalflow/tool/dify_transformer/  +  src/goalflow/visitor/node_visitor.py  ──►  src/goalflow/workflow/generated/<name>.py
```

### Stage 1 — parse (`src/goalflow/dify_parser/`)

`DifyDslParser(dsl_path).parse() -> DifyDslDefinition`:

1. Reads the YAML and applies environment-portability rewrites **on an in-memory copy** — hard-coded internal service URLs/hosts are replaced with `os.environ[...]` references before parsing. The parse is **read-only**: your original export file is never modified.

   > [!NOTE]
   > The substitution table is the class attribute `DifyDslParser.DEFAULT_HOST_SUBSTITUTIONS` (a `{old: new}` dict). Pass `host_substitutions=` to the constructor to override it, or `{}` to disable rewriting entirely. Adapt the table to your own environment's hostnames.

2. Loads YAML (`CSafeLoader`) and builds `DifyDslDefinition` from three sections: `app`, `dependencies`, `workflow`.
3. `_parse_workflow` reads `conversation_variables`, `environment_variables`, and `graph.{nodes,edges}`. Each node → a typed `Dify*NodeData` object; each edge → a `DifyGraphEdge`.
4. `DifyWorkflow.init_graph_data()` builds lookup maps: `node_map`, the single `start_node_id` (errors on none/multiple), `parent_children_node_map` (for iteration/loop subgraphs), and both edge direction maps.

Key classes live in `src/goalflow/dify_parser/dify_app.py` (`DifyWorkflow`, `DifyDslDefinition`, `DifyAppNode`) and `src/goalflow/dify_parser/dify_types.py` (all `Dify*NodeData` models, enums).

### Stage 2 — generate (`src/goalflow/tool/dify_transformer/` + `src/goalflow/visitor/`)

`WorkflowCodeGenerator(dsl_path, *, file_name="workflow.py", class_name=None, out_path=None)`:

- `generate()` parses the DSL, wires up a `DifyNodeVisitor`, calls `do_generate()`, writes the result, and returns the path it wrote to. By default it writes to `src/goalflow/workflow/generated/<file_name>`; pass `out_path` (a full file path or a directory) to write elsewhere.
- The **visitor** (`src/goalflow/visitor/node_visitor.py`) implements a classic double-dispatch: `visit(node)` reads `WfNodeType.value_of(node.data.type)` and dispatches to `visit_start`, `visit_llm`, `visit_code`, `visit_if_else`, `visit_iteration`, `visit_loop`, `visit_tool`, `visit_answer`, `visit_end`, `visit_classifier`, `visit_knowledge_retrieval`, `visit_assigner`, `visit_agent`, `visit_template_transform`, `visit_variable_aggregator`, `visit_doc_extractor` (fallback `visit_generic`).
- The concrete `DifyNodeVisitor` appends **Python source strings** (not objects): node constructors into `node_code_fragments`, edges into `edge_code_fragments`. `_process_edges` computes `next_node_ids`, `fail_branch_node_ids`, and `source_handle_target_map` (branch routing for if/else and classifier).
- `do_generate` maps `app.mode` to `WF_TYPE_WORKFLOW` / `WF_TYPE_CHATFLOW`, emits imports, and templates the class.

## Running the transformer

The transformer is a command-line tool. Run it as a module from the project root:

```bash
python -m goalflow.tool.dify_transformer.wf_transformer_tool \
    --dsl path/to/my_flow.yml \
    --out my_flow_workflow.py \
    --class MyFlowWorkflow
```

- `--dsl` (required) — path to the Dify DSL export. Validated to exist.
- `--out` (optional) — output filename, directory, or full path. If omitted, writes to `src/goalflow/workflow/generated/workflow.py`. If a bare filename, it lands in the default `generated/` directory; if a directory or full path, it's written there.
- `--class` (optional) — the generated workflow class name.

On success it prints the path it wrote to; a missing `--dsl` exits with a non-zero status.

You can also call `WorkflowCodeGenerator` directly in Python (e.g. to batch-transpile):

```python
from goalflow.tool.dify_transformer.wf_code_generator import WorkflowCodeGenerator

written = WorkflowCodeGenerator(
    "path/to/my_flow.yml",
    file_name="my_flow_workflow.py",
    class_name="MyFlowWorkflow",
    # out_path="some/dir/",   # optional; defaults to workflow/generated/
).generate()
print(written)
```

## Anatomy of a generated workflow

The generated file defines a class extending `BaseWorkflow[BaseState]`:

```python
class MyFlowWorkflow(BaseWorkflow[BaseState]):

    def _setup_environment_variables(self):
        # rehydrate EnvironmentVariable objects from the DSL
        ...

    def _setup_conversation_variables(self):
        # rehydrate ConversationVar objects from the DSL
        ...

    def _setup_nodes(self):
        common_args = self._fix_common_args(...)
        start = StartNode(id="start", **common_args, ...)
        self.nodes.append(start)
        self.graph.add_node("start", start)

        branch = IfElseNode(id="if-1", cases=[...], **common_args)
        self.nodes.append(branch)
        self.graph.add_node("if-1", branch)
        # ... one block per node

    def _setup_edges(self):
        self.append_edge(GraphEdge(
            id="e1", source="start", source_handle="source",
            target="if-1", target_handle="target",
            source_type="start", target_type="if-else",
            is_in_iteration=None, is_in_loop=None,
        ))
        # ... one per edge
```

`BaseWorkflow.__init__` reads the `state_schema` from the generic parameter, creates the `StateGraph`, and (via `build_graph`/`_analysis_node_level`) assigns node levels and compiles the graph.

## Registering the generated workflow

Import the generated class and add it to the API-key map in `src/goalflow/api/auth_validator.py` — see [getting-started.md](getting-started.md#5-register-a-workflow).

## Supporting other visual tools

The parser and the generator are cleanly separated by the internal graph model. To support a builder other than Dify, write a new parser that produces the same `DifyWorkflow`/graph-model shape (or a shared abstraction), and the existing visitor/generator can emit code unchanged. This is the intended extension path for "one-click transpile from any visual tool."
