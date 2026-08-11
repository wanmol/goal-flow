"""Agent context management: Protocol + default conversation-history implementation.

``ContextManager`` is responsible for:
- ``assemble``: inject history/context (``before_agent``)
- ``save_turn``: persist this turn's user query + final assistant reply (``after_agent``, excluding intermediate agent-loop messages)

Business code may inject a custom implementation; ``ContextMiddleware`` bridges it with LangGraph state.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_kit.runtimes.base import extract_chunk_text
#from config import get_logger
import logging

if TYPE_CHECKING:
    from agent_kit.harness.middleware.agent_state import ContextAgentState
    from langgraph.runtime import Runtime
    from langgraph.typing import ContextT


#logger = get_logger(__name__)
logger = logging.getLogger(__name__)

DEFAULT_HISTORY_WINDOW_SIZE = 20

ContextAssembleFn = Callable[
    ["ContextAgentState", "Runtime[Any]"],
    list[Any] | None,
]
ContextSaveTurnFn = Callable[
    ["ContextAgentState", "Runtime[Any]", str, str],
    None,
]


@runtime_checkable
class ContextManager(Protocol):
    """Context management plugin protocol."""

    def assemble(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
    ) -> list[Any] | None:
        """Assemble the history/context messages to inject (excluding this turn's user query)."""

    def save_turn(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
        *,
        query: str,
        answer: str,
    ) -> None:
        """Persist this turn's Q&A (only the final user query + assistant reply)."""


class CallableContextManager:
    """Wrap assemble / save functions into a ``ContextManager``."""

    def __init__(
        self,
        assemble_fn: ContextAssembleFn,
        save_fn: ContextSaveTurnFn | None = None,
    ):
        self._assemble_fn = assemble_fn
        self._save_fn = save_fn

    def assemble(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
    ) -> list[Any] | None:
        return self._assemble_fn(state, runtime)

    def save_turn(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
        *,
        query: str,
        answer: str,
    ) -> None:
        if self._save_fn is not None:
            self._save_fn(state, runtime, query, answer)


class _ExtractorAdapter:
    """Adapt a legacy extractor that only has ``extract`` into a ``ContextManager``."""

    def __init__(self, extractor: Any):
        self._extractor = extractor

    def assemble(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
    ) -> list[Any] | None:
        return self._extractor.extract(state, runtime)

    def save_turn(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
        *,
        query: str,
        answer: str,
    ) -> None:
        return None


def history_dicts_to_messages(
    history: list[dict[str, Any]],
    *,
    max_size: int = DEFAULT_HISTORY_WINDOW_SIZE,
) -> list[Any]:
    """Convert MessageService-format history records into LangChain messages (strict user/assistant alternation)."""
    if not history:
        return []
    
    logger.info(f"history_dicts_to_messages history: {history}")

    max_pairs = (max_size // 2) * 2
    if max_pairs > 0 and len(history) > max_pairs:
        history = history[-max_pairs:]

    messages: list[Any] = []
    expected_role = "user"
    for h in history:
        if not isinstance(h, dict):
            continue
        role = h.get("role")
        content = h.get("text") or h.get("content") or ""
        if not content or role not in ("user", "assistant"):
            continue
        if role != expected_role:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
            expected_role = "assistant"
        else:
            messages.append(AIMessage(content=content))
            expected_role = "user"

    if messages and isinstance(messages[-1], HumanMessage):
        messages.pop()

    return messages


def extract_turn_query(messages: list[Any]) -> str:
    """Extract this turn's user query (the agent loop usually no longer appends a HumanMessage)."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            text = extract_chunk_text(msg.content).strip()
            if text:
                return text
    return ""


def extract_turn_answer(messages: list[Any]) -> str:
    """Extract this turn's final assistant reply, skipping intermediate messages like tool call / tool result."""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            continue
        if not isinstance(msg, AIMessage):
            continue
        if getattr(msg, "tool_calls", None):
            continue
        text = extract_chunk_text(msg.content).strip()
        if text:
            return text
    return ""


def _context_field(runtime: "Runtime[Any]", name: str, default: str = "") -> str:
    ctx = runtime.context
    if ctx is None:
        return default
    value = getattr(ctx, name, None)
    if value is None and hasattr(ctx, "get"):
        value = ctx.get(name)
    if value is None:
        return default
    return str(value)


class ConversationHistoryContextManager:
    """Default implementation: pull history from MessageService; optionally persist this turn's Q&A to MessageService."""

    def __init__(self, *, default_history_window_size: int = DEFAULT_HISTORY_WINDOW_SIZE):
        self.default_history_window_size = default_history_window_size

    def assemble(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
    ) -> list[Any] | None:
        logger.info(f"assemble state: {state}")
        logger.info(f"assemble runtime: {runtime}")
        
        conversation_id = runtime.context.sys_conversation_id or state.get("sys_conversation_id", "")
        
        user_id = state.get("sys_user_id") or ""
        app_id = state.get("sys_app_id") or ""
        
        logger.info(f"assemble conversation_id: {conversation_id}, user_id: {user_id}, app_id:{app_id}")
        
        if not conversation_id:
            return None

        try:
            from service.message_service import MessageService

            history = MessageService.get_llm_template_by_conversation_id(
                conversation_id=conversation_id
            )
        except Exception as e:
            logger.warning(
                "ConversationHistoryContextManager assemble failed",
                conversation_id=conversation_id,
                error=str(e),
            )
            return None

        if not history:
            logger.info(f"{conversation_id} assemble history is empty")
            return None

        history = list(history)[::-1]
        # TODO: get history_window_size from runtime.context
        max_size = self.default_history_window_size
        messages = history_dicts_to_messages(history, max_size=max_size)
        return messages or None

    def save_turn(
        self,
        state: "ContextAgentState",
        runtime: "Runtime[ContextT]",
        *,
        query: str,
        answer: str,
    ) -> None:
        conversation_id = _context_field(runtime, "sys_conversation_id")
        if not conversation_id or not query:
            return

        from db.message import Message
        from service.message_service import MessageService

        scene_type = _context_field(runtime, "sys_scene_type", "WANMOL")
        MessageService.create(
            Message(
                conversation_id=conversation_id,
                query=query,
                answer=answer or None,
                message_id=str(uuid.uuid4()),
                creator_id=_context_field(runtime, "sys_user_id"),
                last_updater_id=_context_field(runtime, "sys_user_id"),
                scene_type=scene_type,
                agent_id=_context_field(runtime, "sys_agent_id"),
            )
        )
        logger.info(
            "ConversationHistoryContextManager saved turn",
            conversation_id=conversation_id,
        )


def default_context_manager(
    *,
    default_history_window_size: int = DEFAULT_HISTORY_WINDOW_SIZE,
) -> ConversationHistoryContextManager:
    """Return the default conversation-history context manager."""
    return ConversationHistoryContextManager(
        default_history_window_size=default_history_window_size
    )


def resolve_context_manager(
    manager: ContextManager | ContextAssembleFn | Any | None = None,
    *,
    default_history_window_size: int = DEFAULT_HISTORY_WINDOW_SIZE,
) -> ContextManager:
    """Resolve the injected manager: ``None`` → default; callable → wrapped; legacy ``ContextExtractor`` → adapted."""
    if manager is None:
        return default_context_manager(
            default_history_window_size=default_history_window_size
        )
    if isinstance(manager, ContextManager):
        return manager
    if callable(manager):
        return CallableContextManager(manager)
    if hasattr(manager, "extract"):
        return _ExtractorAdapter(manager)
    raise TypeError(f"Unsupported context manager type: {type(manager)!r}")


def should_save_turn(
    runtime: "Runtime[Any]",
    *,
    default: bool = False,
) -> bool:
    """Whether to save this turn's Q&A: runtime.context takes priority, otherwise use the middleware's constructor argument."""
    ctx = runtime.context
    if ctx is None:
        return default
    if hasattr(ctx, "save_context_turn"):
        return bool(ctx.save_context_turn)
    if hasattr(ctx, "get"):
        value = ctx.get("save_context_turn")
        if value is not None:
            return bool(value)
    return default
