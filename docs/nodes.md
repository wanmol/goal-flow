**English** | [简体中文](nodes.zh-CN.md)

# Nodes Reference

Nodes are the building blocks of a workflow. Each is a subclass of `BaseNode` (`src/goalflow/node/base.py`) and a LangGraph-callable. This page covers the base abstraction, then every built-in node.

The node type registry is `WfNodeType` in [`constants.py`](../src/goalflow/constants.py); each type maps 1:1 to a Dify node type string, which is how the [transpiler](dify-transformer.md) knows which node class to emit.

## The base node

`BaseNode(ABC, Generic[GenericState])` — root of all nodes.

### What you implement

Exactly one method:

```python
def call(self, state: GenericState) -> NodeOutput: ...
```

`NodeOutput` is a union that encodes both **state updates** and **routing**:

| Return type | Meaning |
|-------------|---------|
| `dict` / `TypedDict` | merge these keys into state, continue to `next_node_ids` |
| `Command(update=..., goto=...)` | update state and jump to specific node(s) |
| `List[str]` | branch routing — pick these outgoing handles |
| `Sequence[Send]` | fan out (map-reduce), one parallel branch per `Send` |
| `None` | no update |

### The lifecycle (`__call__`)

Every node runs through the same wrapper so you get consistent timing, logging, fan-in, and error handling for free:

1. Record `start_time` (`time.perf_counter()`) and log **"node started"** with `step`, `node_level`, `wf_name`, `node_type`, `node_id`, `node_title` (plus `iteration_round` when `isInIteration`).
2. `pre_call(state)` — **fan-in barrier**. If the node has more than one `pre_node_ids` and hasn't yet reached its topological depth (`node_level >= step + 1`), it returns `Command(update={"step": step+1}, goto=[self.id])` to re-queue itself, so it only truly runs once all upstream branches have arrived. (`END`/`ANSWER` skip this.)
3. `self.call(state)` — **your logic**.
4. From the returned `Command`, extract `goto` → `next_node_ids` and `update` → `output`, pass `output` through `truncate_output_value`, compute `cost_time`, and log **"node finished"** (with `iteration_item` when `isInIteration`).
5. Bump `step` into `value.update` and return it — **except** `END`/`ANSWER`, which return their raw output without bumping `step`.
6. On exception → re-raise (the outer runner catches it and emits an error event to the frontend).

### Key attributes

`id`, `title`, `desc`, `type`, `variables`, `error_strategy`, `default_value`, `pre_node_ids`, `next_node_ids`, `fail_branch_node_ids`, `parent_node_id`, `node_level`, `wf_name`, plus loop/iteration flags `isInIteration`, `isInLoop`, `iteration_id`, `loop_id`.

### Routing & errors

- **Edges** are declared by the workflow as `GraphEdge`s; the transpiler resolves them into each node's `next_node_ids`, `fail_branch_node_ids`, and `source_handle_target_map` (for branch nodes).
- **`node_level`** is a topological depth assigned by `BaseWorkflow._analysis_node_level`, used with `step` for fan-in.
- **Error strategy** (`error_strategy`, from Dify config):
  - `default-value` — on failure, emit `default_value` and continue normally.
  - `fail-branch` — on failure, emit `source_handle="fail-branch"` and route to `fail_branch_node_ids`.

## Node catalog

Each node maps to a `WfNodeType` and its Dify equivalent.

### Flow control

| Node | Type | Purpose |
|------|------|---------|
| **StartNode** | `start` | Entry. Validates declared inputs (required / type / select / default), seeds `input_variables`, loads `conversation_variables` from DB, exposes `sys.query`. |
| **EndNode** | `end` | Terminal. Resolves output selectors and returns `{"outputs": ...}`. Does not bump `step`. |
| **AnswerNode** | `answer` | Chatflow terminal. Interpolates a text template with variable chunks and streams it (via `AnswerEndStreamOutRouter`). |
| **IfElseNode** | `if-else` | Evaluates ordered cases with `ConditionProcessor`; routes by `selected_case_id` (falls back to `"false"`). |
| **ClassifierNode** | `question-classifier` | LLM picks a category; routes via `source_handle_target_map[category_id]`. |

### Data & transform

| Node | Type | Purpose |
|------|------|---------|
| **CodeNode** | `code` | Runs sandboxed Python (`exec` with restricted `__builtins__`). Requires a `main()` returning a dict; output filtered to declared `outputs`. |
| **TemplateTransformNode** | `template-transform` | Renders a Jinja2 template to `output`. |
| **AggregatorNode** | `variable-aggregator` | Returns the first non-null across `variable_selectors`; supports grouped mode via `advanced_settings`. |
| **AssignerNode** | `assigner` | Variable operations (over-write / append / extend / add / subtract / clear / set …). Persists conversation variables to DB. |
| **DocExtractorNode** | `document-extractor` | Extracts text from uploaded files by MIME type (pdf, docx, xlsx, ppt, epub, eml, csv, …). |

### LLM & agents

| Node | Type | Purpose |
|------|------|---------|
| **LLMNode** | `llm` | Core LLM call. Builds a prompt from `model` / `prompt_template` / `memory` / `context` / `vision`, streams, supports JSON extraction and error strategy. |
| **AgentNode** | `agent` | Manual ReAct loop: binds tools to an Azure/Tongyi LLM, runs `handle_tool_calls`, makes a second call for the final answer, up to 3 retries. |
| **AgentBaseNode** | (base) | New-generation agent base (ADR-004) built on the vendored `agent_kit`'s `Agent` + graph builders. Subclasses implement `output_schema`, `build_prompt`, `build_command`. See [agent-kit.md](agent-kit.md). |

### External & retrieval

| Node | Type | Purpose |
|------|------|---------|
| **HttpRequestNode** | `http-request` | Templated HTTP request (url/headers/params/body), SSE support, retry/timeout, fail-branch/default-value. |
| **ToolNode** | `tool` | Executes a bound external tool function per `tool_provider_config`, with exponential-backoff retry (non-retryable: `ValueError`, `TypeError`, …). |
| **KnowledgeRetrievalNode** | `knowledge-retrieval` | Deprecated stub returning an empty result (kept for graph compatibility). |

### Iteration & loop

| Node | Type | Purpose |
|------|------|---------|
| **IterationNode** (+ `IterationStartNode`) | `iteration` | Builds an inner `StateGraph` and fans out over `iterator_selector` using `Send` (supports `parallel_nums` / `is_parallel`), collecting `output_selector`. |
| **LoopNode** (+ `LoopStartNode`, `LoopEndNode`) | `loop` | Runs a subgraph up to `loop_count` (hard cap 10), resetting `step=0` each pass and checking `break_conditions`. `LoopEndNode` can signal early exit. |

### Custom nodes (`src/goalflow/node/custom/`)

These are domain-specific examples showing how to add your own node types:

| Node | Type | Purpose |
|------|------|---------|
| **NaturalLanguageQueryNode** | `nl_db_query` | A full text-to-SQL ReAct sub-graph: list tables → get schema → generate SQL → check → run. |
| **SensitiveWordCheckNode** | `sensitive_word_check` | Runs `text_to_img_check`; outputs `passed` / `status`. |

## Adding a new node type

1. Subclass `BaseNode[YourState]` and implement `call(self, state)`.
2. Add a `WfNodeType` entry in `src/goalflow/constants.py` if it maps to a new Dify type.
3. Export it from `src/goalflow/node/__init__.py`.
4. Add a `visit_<type>` handler in `src/goalflow/visitor/node_visitor.py` so the transpiler can emit it (if you want DSL support).

For agent-style nodes, prefer subclassing `AgentBaseNode` (see [agent-kit.md](agent-kit.md)) over the manual `AgentNode` loop.

## How nodes become a running graph

The [transpiler](dify-transformer.md) generates a `BaseWorkflow` subclass whose `_setup_nodes` constructs these node objects and `_setup_edges` builds the `GraphEdge`s. `BaseWorkflow.__init__` runs both, adds the nodes to a LangGraph `StateGraph`, assigns node levels via `_analysis_node_level`, and compiles it with the MySQL checkpointer. See [architecture.md](architecture.md#the-node-execution-model).
