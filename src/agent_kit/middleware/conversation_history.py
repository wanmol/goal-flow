"""``ConversationHistoryMiddleware``：``ContextMiddleware`` 的语义化别名。

``ContextMiddleware`` 仍在 ``agent_kit.harness.middleware.context_middleware``
原位保留并可继续 import；本模块以更精确的命名 re-export，让业务
``from agent_kit.middleware import ConversationHistoryMiddleware`` 更直观。
"""
from agent_kit.harness.middleware.context_middleware import (
    ContextMiddleware as ConversationHistoryMiddleware,
)
from agent_kit.harness.middleware.context_middleware import (
    merge_context_messages,
)

__all__ = ["ConversationHistoryMiddleware", "merge_context_messages"]
