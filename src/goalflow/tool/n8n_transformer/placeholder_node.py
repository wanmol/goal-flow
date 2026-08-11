"""PlaceholderNode: placeholder implementation for n8n nodes with no corresponding goalflow node during conversion.

Design intent:
- n8n has hundreds of node types, while goalflow only covers a core subset. When conversion encounters an unsupported type,
  a placeholder node is generated to keep the whole graph structure complete, compilable, instantiable, and runnable along edges.
- The placeholder node is a pure passthrough: it does no business logic, only returns ``next_node_ids`` as goto.
- The original n8n type and parameters are kept on ``n8n_type`` / ``n8n_parameters`` for manual completion.
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
    """Passthrough placeholder node. Handles n8n node types not supported by goalflow."""

    __node_type = WfNodeType.CODE  # Borrow an existing type to avoid special-casing in init_graph_data

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
