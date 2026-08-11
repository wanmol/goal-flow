"""StreamingBridgeMiddleware: bridge the stream callback from RunnableConfig to token pushing.

Design intent: replaces ``AgentRuntime``'s old approach of holding ``stream_callback`` via a ContextVar.
The new approach is LangChain's standard "config travels with the call" -- during ``Agent.run(state, query, config=...)``
the business puts the callback into ``RunnableConfig.configurable["stream_callback"]``, and the middleware reads it out.

Mechanism: the ``after_model`` hook reads out the AIMessage at the end of the response and pushes it split by token.
True token-level streaming (pushing once per chunk) requires the graph to be driven with ``.astream(stream_mode='messages')``;
this middleware provides the accompanying callback reading and triggering logic.

Business usage::

    def on_token(text: str) -> None:
        print(text, end="", flush=True)

    agent.run(state, query, config={"configurable": {"stream_callback": on_token}})
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

logger = logging.getLogger(__name__)

StreamCallback = Callable[[str], None]


def _extract_text(content: Any) -> str:
    """Normalize AIMessage.content to a string (compatible with the list-of-dict form)."""
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
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "".join(parts)
    return str(content)


class StreamingBridgeMiddleware(
    AgentMiddleware[ContextAgentState, ContextT, ResponseT]
):
    """Push model output to ``RunnableConfig.configurable["stream_callback"]``.

    Constructor parameters:
    - ``config_key``: read the callback from ``runtime.config["configurable"][config_key]``;
      default ``"stream_callback"``
    - ``push_on``: ``"after_model"`` trigger timing (default). Set to ``"none"`` to disable auto-pushing
      (only inject the callback into state, driven by the business itself)
    """

    def __init__(
        self,
        *,
        config_key: str = "stream_callback",
        push_on: str = "after_model",
    ):
        self._config_key = config_key
        self._push_on = push_on

    def _resolve_callback(
        self, runtime: "Runtime[ContextT]"
    ) -> Optional[StreamCallback]:
        cfg = getattr(runtime, "config", None) or {}
        configurable = cfg.get("configurable") if isinstance(cfg, dict) else None
        if not configurable:
            return None
        cb = configurable.get(self._config_key)
        return cb if callable(cb) else None

    @override
    def after_model(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        if self._push_on != "after_model":
            return None
        cb = self._resolve_callback(runtime)
        if cb is None:
            return None
        messages = state.get("messages") or []
        if not messages:
            return None
        last = messages[-1]
        if not isinstance(last, AIMessage):
            return None
        # Skip pure tool_call (no text content)
        if getattr(last, "tool_calls", None) and not last.content:
            return None
        text = _extract_text(last.content)
        if not text:
            return None
        try:
            cb(text)
        except Exception as e:
            logger.warning(f"StreamingBridgeMiddleware: callback raised: {e}")
        return None
