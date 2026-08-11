"""n8n JSON → typed N8nWorkflow parser.

Read-only parsing: does not modify the user's export file.

connections structure (keyed by the source node **name**)::

    "connections": {
      "Start": {
        "main": [                     # output type
          [                           # output index 0 (the true branch for an IF node)
            {"node": "HTTP", "type": "main", "index": 0}
          ],
          [ ... ]                     # output index 1 (the false branch for an IF node)
        ]
      }
    }
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from goalflow.config import get_logger
from goalflow.n8n_parser.n8n_app import N8nEdge, N8nWorkflow
from goalflow.n8n_parser.n8n_types import N8nConnectionTarget, N8nNode

logger = get_logger(__name__)


class N8nParser:
    def __init__(self, json_path: Optional[str] = None):
        self.json_path = json_path

    def parse(self) -> N8nWorkflow:
        if not self.json_path:
            raise ValueError("json_path is None")
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.parse_data(data)

    def parse_data(self, data: Dict[str, Any]) -> N8nWorkflow:
        if not isinstance(data, dict):
            raise ValueError("n8n workflow JSON 顶层必须是对象")

        raw_nodes = data.get("nodes")
        if not isinstance(raw_nodes, list):
            raise ValueError("n8n workflow JSON 缺少 nodes 数组")

        workflow = N8nWorkflow(name=data.get("name", ""))

        # 1. Parse nodes (skip disabled ones)
        for raw in raw_nodes:
            node = N8nNode.from_json(raw)
            if node.disabled:
                logger.info("skip disabled n8n node", node=node.name)
                continue
            workflow.add_node(node)

        # 2. Build the name↔id mapping and start node first (edge parsing needs to look up ids by name)
        workflow.init_graph_data()

        # 3. Expand connections → edges
        self._parse_connections(data.get("connections", {}), workflow)

        # connections may introduce new incoming-edge info, but start node detection was done above;
        # if the earlier "no incoming edge" fallback picked wrong, recomputing here is safer.
        workflow.init_graph_data()

        return workflow

    def _parse_connections(
        self, connections: Dict[str, Any], workflow: N8nWorkflow
    ):
        if not isinstance(connections, dict):
            return

        for source_name, output_types in connections.items():
            source_node = workflow.get_node_by_name(source_name)
            if source_node is None:
                # The target is a disabled node or the name does not exist, skip
                logger.warning("n8n connection source not found", source=source_name)
                continue
            if not isinstance(output_types, dict):
                continue

            for output_type, output_slots in output_types.items():
                # output_slots: List[List[target]], the outer index = the output port number
                if not isinstance(output_slots, list):
                    continue
                for output_index, targets in enumerate(output_slots):
                    if not isinstance(targets, list):
                        continue
                    for raw_target in targets:
                        target = N8nConnectionTarget.from_json(raw_target)
                        target_node = workflow.get_node_by_name(target.node)
                        if target_node is None:
                            logger.warning(
                                "n8n connection target not found",
                                source=source_name,
                                target=target.node,
                            )
                            continue
                        workflow.add_edge(
                            N8nEdge(
                                source=source_node.id,
                                target=target_node.id,
                                source_output_index=output_index,
                                source_output_type=output_type,
                                target_input_index=target.index,
                            )
                        )
