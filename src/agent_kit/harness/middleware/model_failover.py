"""ModelFailoverMiddleware: primary/backup model switching middleware.

Design intent: automatically switch to a backup model and retry when the primary model is
"unavailable". Relies on the LangChain middleware protocol's ``wrap_model_call`` hook -- it wraps
the real LLM call, can catch exceptions, and retries with a different model via
``request.override(model=backup)``.

Definition of "unavailable" (default ``should_failover``):
- Infrastructure failures: timeout / connection failure / HTTP 5xx (reuses ``external_errors.is_transport_error``)
- Rate limiting: HTTP 429 / ``RateLimitError``

**Not considered "unavailable"** (default: no switch, exception re-raised as-is):
- Sensitive-word / content-moderation interception (usually manifests as ``ValueError`` / ``ContentFilterFinishReasonError``
  / business return codes) -- switching to a backup is pointless, the backup would be intercepted too
- Programming errors (``TypeError`` / ``AttributeError`` etc.) -- should be surfaced as soon as possible

Division of labor with neighboring middleware:
- ``ModelFailoverMiddleware``: on error, switch to **another model** and retry (this file)
- ``FallbackReplyMiddleware``: on error, return **fixed text** without retrying
- The two can be composed -- failover on the outer layer, raising after all backups fail, caught by the inner fallback::

      middleware=[
          ModelFailoverMiddleware(backup_model),
          FallbackReplyMiddleware("Service is busy, please try again later"),
      ]
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState
from agent_kit.runtimes.external_errors import (
    is_programming_error,
    is_transport_error,
)

logger = logging.getLogger(__name__)


# should_failover(exception) -> whether to switch to a backup model
FailoverPredicate = Callable[[BaseException], bool]


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Rate-limit detection.

    No hard dependency on openai: match by class name ``RateLimitError`` first, then fall back to
    ``status_code == 429`` (compatible with status-bearing exceptions like ``openai.APIStatusError`` /
    ``requests.HTTPError``).
    """
    if type(exc).__name__ == "RateLimitError":
        return True
    # openai.APIStatusError hangs status_code on the exception
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    # requests.HTTPError: status is on response
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 429:
        return True
    return False


def default_should_failover(exc: BaseException) -> bool:
    """Default "unavailable" decision: switch only on infrastructure failures + rate limiting.

    Programming errors never switch (should be surfaced as soon as possible); business exceptions
    like sensitive words (``ValueError`` etc.) are not "unavailable", returning ``False`` → exception re-raised as-is.
    """
    if is_programming_error(exc):
        return False
    return is_transport_error(exc) or _is_rate_limit_error(exc)


class ModelFailoverMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """Primary/backup model switching middleware.

    Constructor arguments:
    - ``*backups``: one or more **already-instantiated** backup ``BaseChatModel``s, degrading in order.
      The primary model comes from ``request.model``, no need to pass it again.
    - ``should_failover``: ``Callable[[BaseException], bool]``, only switches when it returns ``True``.
      Defaults to ``default_should_failover`` (infrastructure failures + rate limiting).

    Behavior:
    - Primary model succeeds → return directly, don't touch backups
    - Primary model raises and ``should_failover(exc)`` is ``True`` → switch to the next backup and retry
    - ``should_failover(exc)`` is ``False`` (e.g. sensitive words) → exception re-raised as-is, no switch
    - Primary + all backups all fail → raise the last exception (leaving it to subsequent middleware to fall back)

    Usage::

        ModelFailoverMiddleware(backup_model)
        ModelFailoverMiddleware(backup_a, backup_b)  # multi-level degradation
        ModelFailoverMiddleware(
            backup_model,
            should_failover=lambda e: "overloaded" in str(e).lower(),
        )
    """

    def __init__(
        self,
        *backups: Any,
        should_failover: Optional[FailoverPredicate] = None,
    ):
        if not backups:
            raise ValueError(
                "ModelFailoverMiddleware: at least one backup model is required"
            )
        self._backups = list(backups)
        self._should_failover = should_failover or default_should_failover

    def _models(self, request: ModelRequest) -> list[Any]:
        """Primary model + backups, in attempt order."""
        return [request.model, *self._backups]

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        models = self._models(request)
        last_exc: Optional[BaseException] = None
        for i, model in enumerate(models):
            try:
                req = request if i == 0 else request.override(model=model)
                return handler(req)
            except Exception as e:
                last_exc = e
                if not self._should_failover(e):
                    # Business exception (sensitive words etc.) / programming error → no switch, re-raise as-is
                    raise
                if i == len(models) - 1:
                    # Already the last backup, nothing to degrade to → raise, leaving it to subsequent middleware to fall back
                    logger.warning(
                        "ModelFailoverMiddleware: all %d model(s) unavailable; "
                        "raising last error (%r)",
                        len(models),
                        e,
                    )
                    raise
                logger.warning(
                    "ModelFailoverMiddleware: model[%d] unavailable (%r); "
                    "failing over to backup[%d]",
                    i,
                    e,
                    i,
                )
        # Theoretically unreachable (the loop either returns or raises)
        assert last_exc is not None
        raise last_exc

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> ModelResponse:
        models = self._models(request)
        last_exc: Optional[BaseException] = None
        for i, model in enumerate(models):
            try:
                req = request if i == 0 else request.override(model=model)
                return await handler(req)
            except Exception as e:
                last_exc = e
                if not self._should_failover(e):
                    raise
                if i == len(models) - 1:
                    logger.warning(
                        "ModelFailoverMiddleware: all %d model(s) unavailable; "
                        "raising last error (%r)",
                        len(models),
                        e,
                    )
                    raise
                logger.warning(
                    "ModelFailoverMiddleware: model[%d] unavailable (%r); "
                    "failing over to backup[%d]",
                    i,
                    e,
                    i,
                )
        assert last_exc is not None
        raise last_exc
