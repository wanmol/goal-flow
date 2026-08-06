"""N8nWorkflow：解析后的 n8n 工作流内存模型。

职责：
- 持有节点列表 + name↔id 映射（n8n connections 用名称，goalflow 图用 id）
- 把 n8n 的 connections{} 展开成扁平的 N8nEdge 列表
- 检测起始（trigger）节点
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from goalflow.n8n_parser.n8n_types import N8nNode


class N8nEdge:
    """一条从源节点到目标节点的有向边。

    - ``source`` / ``target`` 为节点 id（已从 n8n 的名称解析而来）
    - ``source_output_index``：n8n main 输出的索引（IF 节点 0=true,1=false）
    - ``source_output_type``：n8n 连接类型（main / ai_tool / ai_languageModel ...）
    """

    __slots__ = [
        "source",
        "target",
        "source_output_index",
        "source_output_type",
        "target_input_index",
    ]

    def __init__(
        self,
        *,
        source: str,
        target: str,
        source_output_index: int = 0,
        source_output_type: str = "main",
        target_input_index: int = 0,
    ):
        self.source = source
        self.target = target
        self.source_output_index = source_output_index
        self.source_output_type = source_output_type
        self.target_input_index = target_input_index


# n8n trigger 节点的短类型名。出现其一即视为工作流入口。
N8N_TRIGGER_SHORT_TYPES = {
    "start",
    "manualTrigger",
    "webhook",
    "scheduleTrigger",
    "cron",
    "trigger",
    "chatTrigger",
    "executeWorkflowTrigger",
    "formTrigger",
    "emailReadImap",
}


class N8nWorkflow:
    """n8n 工作流的内存模型。"""

    def __init__(self, *, name: str = "", nodes: Optional[List[N8nNode]] = None):
        self.name = name
        self.nodes: List[N8nNode] = nodes or []
        self.edges: List[N8nEdge] = []

        self.node_by_name: Dict[str, N8nNode] = {}
        self.node_by_id: Dict[str, N8nNode] = {}
        self.start_node_id: Optional[str] = None

        self._edge_source_map: Dict[str, List[N8nEdge]] = defaultdict(list)
        self._edge_target_map: Dict[str, List[N8nEdge]] = defaultdict(list)

    def add_node(self, node: N8nNode):
        self.nodes.append(node)

    def get_node(self, node_id: str) -> Optional[N8nNode]:
        return self.node_by_id.get(node_id)

    def get_node_by_name(self, name: str) -> Optional[N8nNode]:
        return self.node_by_name.get(name)

    def add_edge(self, edge: N8nEdge):
        self.edges.append(edge)
        self._edge_source_map[edge.source].append(edge)
        self._edge_target_map[edge.target].append(edge)

    @property
    def edge_source_map(self) -> Dict[str, List[N8nEdge]]:
        return self._edge_source_map

    @property
    def edge_target_map(self) -> Dict[str, List[N8nEdge]]:
        return self._edge_target_map

    def get_outgoing_edges(self, node_id: str) -> List[N8nEdge]:
        return self._edge_source_map.get(node_id, [])

    def is_trigger(self, node: N8nNode) -> bool:
        return node.short_type in N8N_TRIGGER_SHORT_TYPES

    def init_graph_data(self):
        """构建 name↔id 映射并检测起始节点。

        起始节点选取规则：
        1. 优先取第一个 trigger 类型节点；
        2. 没有 trigger 时，取没有入边的第一个节点（源节点）。
        """
        self.node_by_name = {}
        self.node_by_id = {}

        for node in self.nodes:
            self.node_by_name[node.name] = node
            self.node_by_id[node.id] = node

        # 起始节点检测：先找 trigger
        for node in self.nodes:
            if self.is_trigger(node):
                self.start_node_id = node.id
                break

        # 没有 trigger：找没有入边的节点
        if self.start_node_id is None:
            targets = {edge.target for edge in self.edges}
            for node in self.nodes:
                if node.id not in targets:
                    self.start_node_id = node.id
                    break

        # 仍然没有（比如空图或全是环）：取第一个节点兜底
        if self.start_node_id is None and self.nodes:
            self.start_node_id = self.nodes[0].id
