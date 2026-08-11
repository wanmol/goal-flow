"""Typed data structures for n8n workflow JSON.

n8n export format (top level)::

    {
      "name": "My Workflow",
      "nodes": [ {node}, ... ],
      "connections": { "<source node name>": {"main": [[{target}, ...], ...]} },
      ...
    }

A single node::

    {
      "parameters": {...},          # node-specific configuration
      "id": "uuid",
      "name": "HTTP Request",       # display name; connections use it as the key (not id)
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [x, y],
      "disabled": false             # optional
    }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class N8nConnectionTarget:
    """A target endpoint in connections.

    Corresponds to ``{"node": "<target node name>", "type": "main", "index": 0}``.
    n8n references the target by node **name**; it is resolved to a node id during parsing.
    """

    __slots__ = ["node", "type", "index"]

    def __init__(self, *, node: str, type: str = "main", index: int = 0):
        self.node = node
        self.type = type
        self.index = index

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "N8nConnectionTarget":
        return cls(
            node=data["node"],
            type=data.get("type", "main"),
            index=int(data.get("index", 0)),
        )


class N8nNode:
    """An n8n node."""

    __slots__ = [
        "id",
        "name",
        "type",
        "type_version",
        "parameters",
        "position",
        "disabled",
        "credentials",
    ]

    def __init__(
        self,
        *,
        id: str,
        name: str,
        type: str,
        type_version: Any = None,
        parameters: Optional[Dict[str, Any]] = None,
        position: Optional[List[float]] = None,
        disabled: bool = False,
        credentials: Optional[Dict[str, Any]] = None,
    ):
        self.id = id
        self.name = name
        self.type = type
        self.type_version = type_version
        self.parameters = parameters or {}
        self.position = position or []
        self.disabled = disabled
        self.credentials = credentials or {}

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "N8nNode":
        return cls(
            id=data.get("id") or data["name"],
            name=data["name"],
            type=data["type"],
            type_version=data.get("typeVersion"),
            parameters=data.get("parameters", {}),
            position=data.get("position", []),
            disabled=bool(data.get("disabled", False)),
            credentials=data.get("credentials", {}),
        )

    @property
    def short_type(self) -> str:
        """The short type name with the namespace prefix removed.

        ``n8n-nodes-base.httpRequest`` → ``httpRequest``;
        ``@n8n/n8n-nodes-langchain.agent`` → ``agent``.
        """
        return self.type.rsplit(".", 1)[-1] if "." in self.type else self.type
