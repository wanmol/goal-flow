from typing import TYPE_CHECKING, Any

from agent_kit.harness.middleware.agent_state import ContextAgentState
from agent_kit.harness.middleware.context_manager import (
    ContextAssembleFn,
    ContextManager,
    extract_turn_answer,
    extract_turn_query,
    resolve_context_manager,
    should_save_turn,
)
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import HumanMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage
from langgraph.typing import ContextT
from typing_extensions import override

#from config import get_logger
import logging

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


#logger = get_logger(__name__)
logger = logging.getLogger(__name__)


def _extract_current_user_message(messages: list[Any]) -> HumanMessage | None:
    """Take the user message injected by this turn's invoke (located at the tail of messages on entering before_agent)."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return None


def merge_context_messages(
    *,
    context_messages: list[Any],
    existing_messages: list[Any],
) -> dict[str, Any]:
    """Merge context messages with this turn's user query into ``[context..., current_query]``."""
    current_user_msg = _extract_current_user_message(existing_messages)
    ordered: list[Any] = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *context_messages]
    if current_user_msg is not None:
        ordered.append(current_user_msg)
    logger.info(f"merged context messages: {ordered}")
    return {"messages": ordered}


class ContextMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """
    Agent context middleware: inject context before execution, optionally save this turn's Q&A after execution.

    Context is injected via the ``ContextManager`` plugin; defaults to ``ConversationHistoryContextManager``.

    Usage::

        ContextMiddleware()
        ContextMiddleware(manager=MyContextManager())
        ContextMiddleware(manager=lambda state, runtime: [...])
        ContextMiddleware(save_turn=True)

    ``save_turn`` (default ``False``) controls whether ``after_agent`` persists this turn's query + final reply;
    it can also be overridden via ``runtime.context.save_context_turn``. Intermediate agent-loop tool messages are not written.
    """

    def __init__(
        self,
        manager: ContextManager | ContextAssembleFn | Any | None = None,
        *,
        extractor: Any | None = None,
        save_turn: bool = False,
        default_history_window_size: int = 20,
    ):
        # extractor is the legacy parameter name; manager takes priority
        resolved = manager if manager is not None else extractor
        self._manager = resolve_context_manager(
            resolved,
            default_history_window_size=default_history_window_size,
        )
        self._save_turn = save_turn

    @override
    def before_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        context_messages = self._manager.assemble(state, runtime)
        if not context_messages:
            return None

        existing = state.get("messages") or []
        return merge_context_messages(
            context_messages=context_messages,
            existing_messages=existing,
        )

    @override
    def after_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        if not should_save_turn(runtime, default=self._save_turn):
            return None

        messages = state.get("messages") or []
        query = extract_turn_query(messages)
        if not query:
            logger.info("ContextMiddleware save_turn skipped: empty query")
            return None

        answer = extract_turn_answer(messages)
        try:
            self._manager.save_turn(state, runtime, query=query, answer=answer)
        except Exception:
            logger.error("ContextMiddleware save_turn failed", exc_info=True)
        return None

    @override
    async def aafter_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        return self.after_agent(state, runtime)
