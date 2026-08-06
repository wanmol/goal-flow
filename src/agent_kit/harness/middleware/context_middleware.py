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
    """取本轮 invoke 注入的用户消息（进入 before_agent 时位于 messages 末尾）。"""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return None


def merge_context_messages(
    *,
    context_messages: list[Any],
    existing_messages: list[Any],
) -> dict[str, Any]:
    """将上下文消息与本轮 user query 合并为 ``[context..., current_query]``。"""
    current_user_msg = _extract_current_user_message(existing_messages)
    ordered: list[Any] = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *context_messages]
    if current_user_msg is not None:
        ordered.append(current_user_msg)
    logger.info(f"merged context messages: {ordered}")
    return {"messages": ordered}


class ContextMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """
    Agent 上下文中间件：执行前注入上下文，执行后可保存本轮问答。

    上下文通过 ``ContextManager`` 插件注入；默认 ``ConversationHistoryContextManager``。

    用法::

        ContextMiddleware()
        ContextMiddleware(manager=MyContextManager())
        ContextMiddleware(manager=lambda state, runtime: [...])
        ContextMiddleware(save_turn=True)

    ``save_turn``（默认 ``False``）控制是否在 ``after_agent`` 持久化本轮 query + 最终 reply；
    也可在 ``runtime.context.save_context_turn`` 覆盖。中间 agent loop 的 tool 消息不会写入。
    """

    def __init__(
        self,
        manager: ContextManager | ContextAssembleFn | Any | None = None,
        *,
        extractor: Any | None = None,
        save_turn: bool = False,
        default_history_window_size: int = 20,
    ):
        # extractor 为旧参数名，优先 manager
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
