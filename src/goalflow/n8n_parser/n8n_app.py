"""N8nWorkflow: the in-memory model of a parsed n8n workflow.

Responsibilities:
- Holds the node list + name↔id mapping (n8n connections use names, the goalflow graph uses ids)
- Expands n8n's connections{} into a flat list of N8nEdge
- Detects the start (trigger) node
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from goalflow.n8n_parser.n8n_types import N8nNode


class N8nEdge:
    """A directed edge from a source node to a target node.

    - ``source`` / ``target`` are node ids (already resolved from n8n's names)
    - ``source_output_index``: the index of the n8n main output (for IF nodes 0=true, 1=false)
    - ``source_output_type``: the n8n connection type (main / ai_tool / ai_languageModel ...)
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


# Short type names of n8n trigger nodes. If any appears, it is treated as a workflow entry point.
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
    """The in-memory model of an n8n workflow."""

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
        """Build the name↔id mapping and detect the start node.

        Start node selection rules:
        1. Prefer the first trigger-type node;
        2. If there is no trigger, take the first node with no incoming edges (a source node).
        """
        self.node_by_name = {}
        self.node_by_id = {}

        for node in self.nodes:
            self.node_by_name[node.name] = node
            self.node_by_id[node.id] = node

        # Start node detection: look for a trigger first
        for node in self.nodes:
            if self.is_trigger(node):
                self.start_node_id = node.id
                break

        # No trigger: find a node with no incoming edges
        if self.start_node_id is None:
            targets = {edge.target for edge in self.edges}
            for node in self.nodes:
                if node.id not in targets:
                    self.start_node_id = node.id
                    break

        # Still none (e.g. an empty graph or all cycles): fall back to the first node
        if self.start_node_id is None and self.nodes:
            self.start_node_id = self.nodes[0].id
