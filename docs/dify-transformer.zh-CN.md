[English](dify-transformer.md) | **简体中文**

# Dify 转译器（DSL → 可运行工作流）

转译器将一份 **Dify DSL 导出文件**（`.yml`）转换为一个**可运行的 LangGraph 工作流** —— 即一个定义了 `BaseWorkflow` 子类的 Python 文件。你在 Dify 中以可视化方式设计流程，导出、转译，然后在本框架的引擎上运行。不依赖 Dify 的运行时。

## 为什么需要它

LangGraph 没有可视化设计器。Dify 有一个出色的设计器，但会把你锁定在它的运行时里。这个转译器在两者之间架起桥梁：用 Dify（未来也可以是其他可视化构建工具）进行快速设计和验证，然后生成归你所有、可以纳入版本控制、可以做 diff 和扩展的代码。

## 两阶段流水线

```
Dify DSL (.yml)
     │
     ▼
[1] src/goalflow/dify_parser/  ──►  internal graph model (DifyDslDefinition / DifyWorkflow)
     │
     ▼
[2] src/goalflow/tool/dify_transformer/  +  src/goalflow/visitor/node_visitor.py  ──►  src/goalflow/workflow/generated/<name>.py
```

### 阶段 1 —— 解析（`src/goalflow/dify_parser/`）

`DifyDslParser(dsl_path).parse() -> DifyDslDefinition`：

1. 读取 YAML 并在**内存副本**上应用环境可移植性改写 —— 硬编码的内部服务 URL/主机会在解析前被替换为 `os.environ[...]` 引用。解析过程是**只读**的:你原始的导出文件永远不会被修改。

   > [!NOTE]
   > 替换表是类属性 `DifyDslParser.DEFAULT_HOST_SUBSTITUTIONS`(一个 `{旧值: 新值}` 字典)。向构造器传入 `host_substitutions=` 可覆盖它,传 `{}` 则完全禁用改写。请根据你自己环境的主机名调整该表。

2. 加载 YAML（`CSafeLoader`）并从三个部分构建 `DifyDslDefinition`：`app`、`dependencies`、`workflow`。
3. `_parse_workflow` 读取 `conversation_variables`、`environment_variables` 以及 `graph.{nodes,edges}`。每个节点 → 一个带类型的 `Dify*NodeData` 对象；每条边 → 一个 `DifyGraphEdge`。
4. `DifyWorkflow.init_graph_data()` 构建查找映射：`node_map`、唯一的 `start_node_id`（没有或存在多个时报错）、`parent_children_node_map`（用于迭代/循环子图），以及两个方向的边映射。

关键类位于 `src/goalflow/dify_parser/dify_app.py`（`DifyWorkflow`、`DifyDslDefinition`、`DifyAppNode`）和 `src/goalflow/dify_parser/dify_types.py`（所有 `Dify*NodeData` 模型、枚举）。

### 阶段 2 —— 生成（`src/goalflow/tool/dify_transformer/` + `src/goalflow/visitor/`）

`WorkflowCodeGenerator(dsl_path, *, file_name="workflow.py", class_name=None, out_path=None)`：

- `generate()` 解析 DSL，接线一个 `DifyNodeVisitor`，调用 `do_generate()`，写入结果并返回实际写入的路径。默认写入 `src/goalflow/workflow/generated/<file_name>`；传入 `out_path`(完整文件路径或目录)可写到别处。
- **访问者（visitor）**（`src/goalflow/visitor/node_visitor.py`）实现了经典的双重分派：`visit(node)` 读取 `WfNodeType.value_of(node.data.type)` 并分派到 `visit_start`、`visit_llm`、`visit_code`、`visit_if_else`、`visit_iteration`、`visit_loop`、`visit_tool`、`visit_answer`、`visit_end`、`visit_classifier`、`visit_knowledge_retrieval`、`visit_assigner`、`visit_agent`、`visit_template_transform`、`visit_variable_aggregator`、`visit_doc_extractor`（兜底为 `visit_generic`）。
- 具体的 `DifyNodeVisitor` 追加的是 **Python 源码字符串**（而非对象）：节点构造器进入 `node_code_fragments`，边进入 `edge_code_fragments`。`_process_edges` 计算 `next_node_ids`、`fail_branch_node_ids` 以及 `source_handle_target_map`（用于 if/else 和分类器的分支路由）。
- `do_generate` 将 `app.mode` 映射为 `WF_TYPE_WORKFLOW` / `WF_TYPE_CHATFLOW`，生成 import 语句，并套用类的模板。

## 运行转译器

转译器是一个命令行工具。从项目根目录以模块方式运行：

```bash
python -m goalflow.tool.dify_transformer.wf_transformer_tool \
    --dsl path/to/my_flow.yml \
    --out my_flow_workflow.py \
    --class MyFlowWorkflow
```

- `--dsl`(必填)—— Dify DSL 导出文件的路径,会校验其存在。
- `--out`(可选)—— 输出文件名、目录或完整路径。省略时写入 `src/goalflow/workflow/generated/workflow.py`。若为纯文件名,则落到默认的 `generated/` 目录;若为目录或完整路径,则写到该处。
- `--class`(可选)—— 生成的工作流类名。

成功时打印实际写入的路径;缺少 `--dsl` 时以非零状态码退出。

你也可以在 Python 中直接调用 `WorkflowCodeGenerator`(例如批量转译):

```python
from goalflow.tool.dify_transformer.wf_code_generator import WorkflowCodeGenerator

written = WorkflowCodeGenerator(
    "path/to/my_flow.yml",
    file_name="my_flow_workflow.py",
    class_name="MyFlowWorkflow",
    # out_path="some/dir/",   # 可选;默认写入 workflow/generated/
).generate()
print(written)
```

## 生成的工作流剖析

生成的文件定义了一个继承自 `BaseWorkflow[BaseState]` 的类：

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

`BaseWorkflow.__init__` 从泛型参数读取 `state_schema`，创建 `StateGraph`，并（通过 `build_graph`/`_analysis_node_level`）为节点分配层级并编译图。

## 注册生成的工作流

导入生成的类，并把它加入 `src/goalflow/api/auth_validator.py` 中的 API key 映射 —— 参见 [getting-started.md](getting-started.md#5-register-a-workflow)。

## 支持其他可视化工具

解析器和生成器通过内部图模型清晰地解耦。要支持 Dify 之外的构建工具，只需编写一个新的解析器，让它产出相同的 `DifyWorkflow`/图模型结构（或某个共享抽象），现有的访问者/生成器即可原样发射代码。这正是"从任意可视化工具一键转译"所设想的扩展路径。
