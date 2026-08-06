"""ConversationStore：会话历史存取的抽象协议。

设计意图：替代 ``ContextManager`` Protocol 的"泛上下文管理"语义。本协议明确
聚焦于"会话历史存取"，与 ``ConversationHistoryMiddleware`` 配对使用。

业务在自己的项目里实现 ``ConversationStore``（包接 MessageService / 接 Redis /
接任意 KV）注入到 middleware：

    middleware=[ConversationHistoryMiddleware(store=MyStore())]
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConversationStore(Protocol):
    """会话历史存取协议。

    实现需提供：

    - ``load_history(conversation_id) -> list[dict]``：返回历史记录。
      每条记录形态 ``{"role": "user"|"assistant", "text"|"content": "..."}``。
      顺序可以是正序或倒序——middleware 会按 ``order`` 参数处理。

    - ``save_turn(conversation_id, query, answer, **meta) -> None``：持久化本轮问答。
    """

    def load_history(self, conversation_id: str) -> list[dict[str, Any]]: ...

    def save_turn(
        self,
        conversation_id: str,
        *,
        query: str,
        answer: str,
        **meta: Any,
    ) -> None: ...
