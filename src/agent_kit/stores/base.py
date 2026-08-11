"""ConversationStore: the abstract protocol for conversation history access.

Design intent: replaces the "generic context management" semantics of the ``ContextManager`` Protocol. This protocol
explicitly focuses on "conversation history access" and is used paired with ``ConversationHistoryMiddleware``.

Business code implements ``ConversationStore`` in its own project (wrapping MessageService / Redis /
any KV) and injects it into the middleware:

    middleware=[ConversationHistoryMiddleware(store=MyStore())]
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConversationStore(Protocol):
    """Conversation history access protocol.

    Implementations must provide:

    - ``load_history(conversation_id) -> list[dict]``: return history records.
      Each record has the shape ``{"role": "user"|"assistant", "text"|"content": "..."}``.
      The order can be ascending or descending -- the middleware handles it per the ``order`` parameter.

    - ``save_turn(conversation_id, query, answer, **meta) -> None``: persist this turn's Q&A.
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
