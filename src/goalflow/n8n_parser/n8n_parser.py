"""n8n JSON → 类型化 N8nWorkflow 解析器。

只读解析：不修改用户的导出文件。

connections 结构（以源节点**名称**为键）::

    "connections": {
      "Start": {
        "main": [                     # 输出类型
          [                           # 输出索引 0（IF 节点即 true 分支）
            {"node": "HTTP", "type": "main", "index": 0}
          ],
          [ ... ]                     # 输出索引 1（IF 节点即 false 分支）
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

        # 1. 解析节点（跳过 disabled）
        for raw in raw_nodes:
            node = N8nNode.from_json(raw)
            if node.disabled:
                logger.info("skip disabled n8n node", node=node.name)
                continue
            workflow.add_node(node)

        # 2. 先建 name↔id 映射与起始节点（边解析需要按名称查 id）
        workflow.init_graph_data()

        # 3. 展开 connections → 边
        self._parse_connections(data.get("connections", {}), workflow)

        # connections 可能引入新的入边信息，但起始节点检测已在上面完成；
        # 若此前靠“无入边”兜底选错，这里重算一次更稳妥。
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
                # 目标是 disabled 节点或名称不存在，跳过
                logger.warning("n8n connection source not found", source=source_name)
                continue
            if not isinstance(output_types, dict):
                continue

            for output_type, output_slots in output_types.items():
                # output_slots：List[List[target]]，外层索引=输出端口序号
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
