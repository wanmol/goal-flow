"""n8n 工作流 JSON 的类型化数据结构。

n8n 导出格式(顶层)::

    {
      "name": "My Workflow",
      "nodes": [ {node}, ... ],
      "connections": { "<源节点名>": {"main": [[{target}, ...], ...]} },
      ...
    }

单个 node::

    {
      "parameters": {...},          # 节点专属配置
      "id": "uuid",
      "name": "HTTP Request",       # 显示名,connections 用它作键(不是 id)
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [x, y],
      "disabled": false             # 可选
    }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class N8nConnectionTarget:
    """connections 里的一个目标端点。

    对应 ``{"node": "<目标节点名>", "type": "main", "index": 0}``。
    n8n 用节点**名称**引用目标,解析时再解析成节点 id。
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
    """一个 n8n 节点。"""

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
        """去掉命名空间前缀的短类型名。

        ``n8n-nodes-base.httpRequest`` → ``httpRequest``；
        ``@n8n/n8n-nodes-langchain.agent`` → ``agent``。
        """
        return self.type.rsplit(".", 1)[-1] if "." in self.type else self.type
