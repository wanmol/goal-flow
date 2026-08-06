"""PlaceholderNode：n8n 转换时无对应 goalflow 节点的占位实现。

设计意图：
- n8n 有成百上千种节点，goalflow 只覆盖核心子集。转换遇到不支持的类型时，
  生成一个占位节点，保证整图结构完整、能编译、能实例化、能按边路由跑通。
- 占位节点是纯透传：不做任何业务，只把 ``next_node_ids`` 作为 goto 返回。
- 原始 n8n 类型与参数保留在 ``n8n_type`` / ``n8n_parameters`` 上，便于人工补齐。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langgraph.types import Command

from goalflow.config import get_logger
from goalflow.constants import WfNodeType
from goalflow.node.base import BaseNode, NodeOutput
from goalflow.state import GenericState

logger = get_logger(__name__)


class PlaceholderNode(BaseNode):
    """透传占位节点。落地 n8n 中 goalflow 未支持的节点类型。"""

    __node_type = WfNodeType.CODE  # 借用一个已有类型，避免 init_graph_data 特判

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(
        self,
        *,
        n8n_type: str = "",
        n8n_parameters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.n8n_type = n8n_type
        self.n8n_parameters = n8n_parameters or {}

    def call(self, state: GenericState) -> NodeOutput:
        logger.warning(
            "PlaceholderNode passthrough (n8n node not implemented in goalflow)",
            node_id=self.id,
            n8n_type=self.n8n_type,
        )
        return Command(
            update={"node_id": self.id},
            goto=self.next_node_ids or [],
        )
