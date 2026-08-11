"""``ConversationHistoryMiddleware``: a semantic alias for ``ContextMiddleware``.

``ContextMiddleware`` is still retained in place at ``agent_kit.harness.middleware.context_middleware``
and can still be imported; this module re-exports it under a more precise name, making
``from agent_kit.middleware import ConversationHistoryMiddleware`` more intuitive for the business.
"""
from agent_kit.harness.middleware.context_middleware import (
    ContextMiddleware as ConversationHistoryMiddleware,
)
from agent_kit.harness.middleware.context_middleware import (
    merge_context_messages,
)

__all__ = ["ConversationHistoryMiddleware", "merge_context_messages"]
