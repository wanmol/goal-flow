"""FallbackReplyMiddleware: error-fallback middleware (replaces the ``AgentRuntime.on_failure`` hook).

Design intent: push the pattern "LLM call raises → fall back with fixed text" down from a Runtime
hook into a standalone LangChain ``AgentMiddleware``, relying on the LangChain middleware protocol's
``wrap_model_call`` hook.

Difference from LangChain's built-in ``ModelFallbackMiddleware``:
- ``ModelFallbackMiddleware``: on error, switch to **another model** and retry
- ``FallbackReplyMiddleware``: on error, directly return **fixed text** without retrying

Applicable scenarios:
- Give the user a friendly fallback prompt when the LLM service is degraded
- Return standard wording after a compliance interception
- Return "please retry later" on network failure

**Not applicable** scenarios (use ``ModelFallbackMiddleware`` or ``ModelRetryMiddleware``):
- You want to retry or switch models
- You want to handle by exception type separately (although this middleware also supports the ``on_error`` callback, its semantics are relatively simple)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import AIMessage
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState


# on_error(exception) -> fallback text
OnErrorFn = Callable[[BaseException], str]


class FallbackReplyMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """Error-fallback middleware.

    Constructor arguments:
    - ``fallback_reply``: default fallback text, used when ``on_error`` is not provided or raises
    - ``on_error``: optional callback ``Callable[[Exception], str]``, returning different text by exception type;
      takes priority over ``fallback_reply``
    - ``catch``: tuple of exception types to catch, default ``(Exception,)``; unmatched exceptions are re-raised as usual

    Usage::

        FallbackReplyMiddleware(fallback_reply="Something went wrong, please try again later")

        # Branch by exception type
        FallbackReplyMiddleware(
            fallback_reply="Something went wrong",
            on_error=lambda e: "Network error" if "timeout" in str(e).lower() else "Unknown error",
        )

        # Catch only network exceptions, let others re-raise as usual
        FallbackReplyMiddleware(
            fallback_reply="Network error",
            catch=(TimeoutError, ConnectionError),
        )
    """

    def __init__(
        self,
        fallback_reply: str = "请稍后再试。",
        *,
        on_error: Optional[OnErrorFn] = None,
        catch: tuple[type[BaseException], ...] = (Exception,),
    ):
        self._fallback_reply = fallback_reply
        self._on_error = on_error
        self._catch = catch

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        try:
            return handler(request)
        except self._catch as e:
            reply = self._resolve_reply(e)
            return ModelResponse(result=[AIMessage(content=reply)], structured_response=None)

    def _resolve_reply(self, error: BaseException) -> str:
        if self._on_error is None:
            return self._fallback_reply
        try:
            text = self._on_error(error)
        except Exception:
            return self._fallback_reply
        return text or self._fallback_reply
