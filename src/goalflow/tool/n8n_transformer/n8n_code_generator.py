"""n8n workflow -> runnable goalflow workflow (.py) code generator.

Modeled on ``goalflow.tool.dify_transformer.wf_code_generator.WorkflowCodeGenerator``:
parse n8n JSON -> traverse nodes/edges -> generate a BaseWorkflow subclass source file.

Node mapping strategy (core subset + placeholder fallback):
- START / END / HTTP_REQUEST / IF_ELSE / CODE: generate real goalflow nodes
- Everything else (including LLM/Agent and various integrations): generate a passthrough PlaceholderNode, recorded in the warning list

Routing: goalflow nodes route dynamically via ``Command(goto=next_node_ids)``,
so only ``graph.add_node`` + setting ``next_node_ids`` is needed, with START additionally getting ``add_edge(START, id)``.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from goalflow.n8n_parser import (
    GoloNodeKind,
    N8nParser,
    N8nWorkflow,
    map_node_kind,
)
from goalflow.n8n_parser.n8n_types import N8nNode

_INDENT = "        "  # 8-space indentation inside method bodies


class N8nCodeGenerator:
    def __init__(
        self,
        json_path: str,
        *,
        file_name: str = "n8n_workflow.py",
        class_name: Optional[str] = None,
        out_path: Optional[str] = None,
    ):
        if json_path is None:
            raise ValueError("json_path is None")
        self.parser = N8nParser(json_path)
        self.file_name = file_name
        self.class_name = class_name
        self.out_path = out_path
        self.generated_code = ""
        # Unsupported nodes collected during conversion, for the CLI to print a warning list
        self.warnings: List[str] = []
        # node id -> variable name in the generated code
        self._var_by_id: Dict[str, str] = {}

    def generate(self) -> str:
        workflow = self.parser.parse()
        code = self.do_generate(workflow)

        filename = self._resolve_output_path()
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        return filename

    def _resolve_output_path(self) -> str:
        if self.out_path is None:
            generated_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "workflow",
                "generated",
            )
            return os.path.join(generated_dir, self.file_name)
        out = os.path.abspath(self.out_path)
        if os.path.isdir(out) or self.out_path.endswith(("/", os.sep)):
            return os.path.join(out, self.file_name)
        return out

    def do_generate(self, workflow: N8nWorkflow) -> str:
        self.generated_code = ""
        self.warnings = []
        self._assign_var_names(workflow)

        self._generate_imports()
        self._generate_class(workflow)
        return self.generated_code

    def _assign_var_names(self, workflow: N8nWorkflow):
        """Assign a unique, valid Python variable name to each node."""
        used = set()
        for node in workflow.nodes:
            base = re.sub(r"\W", "_", node.name).strip("_").lower() or "node"
            base = f"n_{base}"
            name = base
            i = 1
            while name in used:
                name = f"{base}_{i}"
                i += 1
            used.add(name)
            self._var_by_id[node.id] = name

    def _generate_imports(self):
        imports = [
            "from typing import Dict, Any",
            "from goalflow.state import GenericState, BaseState",
            "from langgraph.graph import StateGraph, START",
            "from goalflow.node import *",
            "from goalflow.workflow_types import *",
            "from goalflow.constants import *",
            "from goalflow.workflow.base_workflow import BaseWorkflow, GraphEdge",
            "from goalflow.tool.n8n_transformer.placeholder_node import PlaceholderNode",
            "import os",
            "import json",
        ]
        self.generated_code += "\n".join(imports) + "\n\n\n"

    def _generate_class(self, workflow: N8nWorkflow):
        class_name = self.class_name or f"N8nWorkflow_{self._safe_ident(workflow.name)}"

        node_code = self._generate_nodes(workflow)
        edge_code = self._generate_edges(workflow)

        class_code = f'''class {class_name}(BaseWorkflow[BaseState]):
    """Generated from n8n workflow: {workflow.name or '(unnamed)'}"""

    def __init__(self, config_schema: str = None, workflow_type: str = "workflow"):
        super().__init__(config_schema, workflow_type)

    def _setup_environment_variables(self):
        self.environment_list = []

    def _setup_conversation_variables(self):
        self.conversation_list = []

    def _setup_nodes(self):
        """Setup all workflow nodes"""
{node_code}

    def _setup_edges(self):
        """Setup all workflow edges"""
{edge_code}
'''
        self.generated_code += class_code

    def _generate_nodes(self, workflow: N8nWorkflow) -> str:
        fragments: List[str] = []
        for node in workflow.nodes:
            kind = map_node_kind(node.short_type)
            next_ids = [e.target for e in workflow.get_outgoing_edges(node.id)]
            is_start = node.id == workflow.start_node_id

            if kind == GoloNodeKind.START:
                fragments.append(self._emit_start(node, next_ids))
            elif kind == GoloNodeKind.HTTP_REQUEST:
                fragments.append(self._emit_http(node, next_ids))
            elif kind == GoloNodeKind.IF_ELSE:
                fragments.append(self._emit_if(node, workflow))
            elif kind == GoloNodeKind.CODE:
                fragments.append(self._emit_code(node, next_ids))
            elif kind == GoloNodeKind.END:
                fragments.append(self._emit_end(node))
            else:
                # LLM / Agent / various integrations -> placeholder fallback
                self.warnings.append(f"{node.name} ({node.type})")
                fragments.append(self._emit_placeholder(node, next_ids, is_start))
        return "\n".join(fragments) if fragments else f"{_INDENT}pass"

    def _generate_edges(self, workflow: N8nWorkflow) -> str:
        fragments: List[str] = []
        start_var = self._var_by_id.get(workflow.start_node_id)
        if start_var:
            fragments.append(f'{_INDENT}self.graph.add_edge(START, "{workflow.start_node_id}")')
        for edge in workflow.edges:
            fragments.append(
                f'{_INDENT}self.append_edge(GraphEdge('
                f'id="{edge.source}->{edge.target}#{edge.source_output_index}", '
                f'source="{edge.source}", source_handle="{edge.source_output_type}", '
                f'target="{edge.target}", target_handle="{edge.target_input_index}", '
                f'source_type="n8n", target_type="n8n"))'
            )
        return "\n".join(fragments) if fragments else f"{_INDENT}pass"

    # -- emit for various node types --

    def _common_args_literal(self, node: N8nNode) -> str:
        return (
            f'desc="{self._esc(node.name)}", selected=False, '
            f'title="{self._esc(node.name)}", type="{{type}}", id="{node.id}"'
        )

    def _emit_start(self, node: N8nNode, next_ids: List[str]) -> str:
        var = self._var_by_id[node.id]
        common = self._common_args_literal(node).replace("{type}", "start")
        return f'''{_INDENT}# start node: {node.name} ({node.type})
{_INDENT}{var} = StartNode(wf_inputs=[], {common})
{_INDENT}{var}.next_node_ids = {next_ids!r}
{_INDENT}self.nodes.append({var})
{_INDENT}self.graph.add_node("{node.id}", {var})'''

    def _emit_http(self, node: N8nNode, next_ids: List[str]) -> str:
        var = self._var_by_id[node.id]
        common = self._common_args_literal(node).replace("{type}", "http-request")
        url = node.parameters.get("url", "")
        method = str(node.parameters.get("method", "GET")).upper()
        return f'''{_INDENT}# http node: {node.name} ({node.type})
{_INDENT}{var} = HttpRequestNode(url={url!r}, method="{method}", body=None,
{_INDENT}    authorization=None, retry_config=None, timeout_config=None,
{_INDENT}    ssl_verify=True, params=None, headers=None, {common})
{_INDENT}{var}.next_node_ids = {next_ids!r}
{_INDENT}self.nodes.append({var})
{_INDENT}self.graph.add_node("{node.id}", {var})'''

    def _emit_code(self, node: N8nNode, next_ids: List[str]) -> str:
        var = self._var_by_id[node.id]
        common = self._common_args_literal(node).replace("{type}", "code")
        # n8n Code nodes run JS, goalflow runs Python. Kept verbatim as a placeholder string + TODO, no guessed translation.
        js = node.parameters.get("jsCode") or node.parameters.get("functionCode") or ""
        code_body = (
            "# TODO: 原 n8n Code 节点为 JavaScript,需人工改写为 Python\n"
            "# 原始 JS:\n"
            + "\n".join("# " + ln for ln in js.splitlines())
            + "\ndef main(params):\n    return {}\n"
        )
        return f'''{_INDENT}# code node: {node.name} ({node.type}) [JS 原样保留待人工改写]
{_INDENT}{var} = CodeNode(code={code_body!r}, code_language="python3", outputs={{}}, {common})
{_INDENT}{var}.next_node_ids = {next_ids!r}
{_INDENT}self.nodes.append({var})
{_INDENT}self.graph.add_node("{node.id}", {var})'''

    def _emit_if(self, node: N8nNode, workflow: N8nWorkflow) -> str:
        var = self._var_by_id[node.id]
        common = self._common_args_literal(node).replace("{type}", "if-else")
        # n8n IF: output index 0=true, 1=false. goalflow routes via source_handle_target_map[case_id].
        true_ids, false_ids = [], []
        for e in workflow.get_outgoing_edges(node.id):
            (true_ids if e.source_output_index == 0 else false_ids).append(e.target)
        handle_map = {"true": true_ids, "false": false_ids}
        all_next = true_ids + false_ids
        return f'''{_INDENT}# if node: {node.name} ({node.type})
{_INDENT}# TODO: n8n IF 条件需人工补齐到 cases;当前默认走 false 分支
{_INDENT}{var} = IfElseNode(logical_operator="and", conditions=[],
{_INDENT}    cases=[Case(case_id="true", logical_operator="and", conditions=[])],
{_INDENT}    source_handle_target_map={handle_map!r}, {common})
{_INDENT}{var}.next_node_ids = {all_next!r}
{_INDENT}self.nodes.append({var})
{_INDENT}self.graph.add_node("{node.id}", {var})'''

    def _emit_end(self, node: N8nNode) -> str:
        var = self._var_by_id[node.id]
        common = self._common_args_literal(node).replace("{type}", "end")
        return f'''{_INDENT}# end node: {node.name} ({node.type})
{_INDENT}{var} = EndNode(outputs=[], {common})
{_INDENT}self.nodes.append({var})
{_INDENT}self.graph.add_node("{node.id}", {var})'''

    def _emit_placeholder(self, node: N8nNode, next_ids: List[str], is_start: bool) -> str:
        var = self._var_by_id[node.id]
        # The placeholder node borrows the code type; if it happens to be the start node, the type is still marked start for runtime recognition
        node_type = "start" if is_start else "code"
        common = self._common_args_literal(node).replace("{type}", node_type)
        params_json = json.dumps(node.parameters, ensure_ascii=False)
        return f'''{_INDENT}# UNSUPPORTED n8n node → placeholder: {node.name} ({node.type})
{_INDENT}{var} = PlaceholderNode(n8n_type="{node.type}",
{_INDENT}    n8n_parameters=json.loads({params_json!r}), {common})
{_INDENT}{var}.next_node_ids = {next_ids!r}
{_INDENT}self.nodes.append({var})
{_INDENT}self.graph.add_node("{node.id}", {var})'''

    @staticmethod
    def _esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _safe_ident(text: str) -> str:
        ident = re.sub(r"\W", "_", text or "").strip("_")
        return ident or "generated"
