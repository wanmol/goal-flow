from typing import TYPE_CHECKING, Any

from agent_kit.harness.middleware.agent_state import ContextAgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.typing import ContextT
from typing_extensions import override

#from config import get_logger

if TYPE_CHECKING:
    from langgraph.runtime import Runtime
    


import logging
#logger = get_logger(__name__)
logger = logging.getLogger(__name__)


_DEFAULT_REJECTION_REPLY = (
    "抱歉，您的输入包含违规内容，无法继续处理。请修改后重试。"
)


def _extract_message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def _get_last_human_message_text(messages: list[Any]) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return _extract_message_text(msg.content).strip()
    return None


class SensitiveCheckMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """
    Runs a sensitive-word check on user input before Agent execution; on failure, short-circuits to end and returns compliance wording.

    The check logic reuses utils.sensitive_identification.

    Optional runtime.context config:
    - sensitive_check_enabled (bool): whether enabled, default True
    - sensitive_check_type (str): "text" | "text_to_img", default "text"
    - sensitive_rejection_reply (str): the reply wording on rejection
    """

    @override
    @hook_config(can_jump_to=["end"])
    def before_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        from utils.sensitive_identification import text_check, text_to_img_check
        _CHECK_TYPE_HANDLERS = {
            "text": text_check,
            "text_to_img": text_to_img_check,
        }

        if runtime.context.get("sensitive_check_enabled", True) is False:
            return None

        messages = state.get("messages") or []
        if not messages:
            return None

        text = _get_last_human_message_text(messages)
        if text is None or not text:
            logger.info("SensitiveCheckMiddleware skipped: empty user text")
            return None

        check_type = runtime.context.get("sensitive_check_type", "text")
        checker = _CHECK_TYPE_HANDLERS.get(check_type)
        if checker is None:
            logger.warning(
                "SensitiveCheckMiddleware unsupported check_type, skipped",
                check_type=check_type,
            )
            return None

        try:
            passed = checker(text)
        except Exception:
            logger.error(
                "SensitiveCheckMiddleware check error, allowing through",
                exc_info=True,
                check_type=check_type,
            )
            return None

        if passed:
            return None

        reply = runtime.context.get(
            "sensitive_rejection_reply", _DEFAULT_REJECTION_REPLY
        )
        logger.info(
            "SensitiveCheckMiddleware rejected",
            check_type=check_type,
        )
        return {"jump_to": "end", "messages": [AIMessage(content=reply)]}

    @override
    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)
