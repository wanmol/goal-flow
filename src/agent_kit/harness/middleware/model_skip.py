"""ModelSkipMiddleware: skip-the-LLM-call middleware (replaces the ``AgentRuntime.should_run_agent`` hook).

Design intent: push the pattern "low-signal ack / cache hit / business side already collected all info
→ produce a reply directly without calling the LLM" down from a Runtime hook into a standalone
LangChain ``AgentMiddleware``.

Difference from ``EntryGuardMiddleware``:
- ``EntryGuardMiddleware`` fires in ``before_agent``, **before** the agent loop
- ``ModelSkipMiddleware`` fires in ``before_model``, **inside** the agent loop but skips the LLM

Applicable scenarios:
- User input is a signal-free ack like "ok"/"sure"/"yeah", saving LLM cost
- Cache hit, directly return the cached reply
- Business side already collected all needed info via another path, no LLM decision needed

**Not applicable** scenarios (keep using the ``should_run_agent`` hook):
- Need ``result.failed = True`` / to go through the full ``finalize`` post-processing flow
- Need to write multiple non-messages state fields
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT, hook_config
from langchain_core.messages import AIMessage
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


# predicate returns (skip_reason, reply_text) to trigger a skip; returns None to keep calling the LLM
SkipResult = Optional[Tuple[str, str]]
SkipPredicate = Callable[[ContextAgentState, "Runtime[Any]"], SkipResult]


class ModelSkipMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """Skip-the-LLM-call middleware.

    Pass ``predicate(state, runtime) -> (skip_reason, reply) | None`` at construction:

    - returns ``None``: allow through, call the LLM normally
    - returns ``("cached", "You have confirmed the order")``: skip the LLM, writing ``AIMessage(content=reply)``
      into messages as the model reply and ending the agent loop

    ``skip_reason`` is only for logging/debugging and does not affect behavior.
    """

    def __init__(self, predicate: SkipPredicate):
        self._predicate = predicate

    @override
    @hook_config(can_jump_to=["end"])
    def before_model(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        result = self._predicate(state, runtime)
        if result is None:
            return None
        _reason, reply = result
        return {"jump_to": "end", "messages": [AIMessage(content=reply)]}

    @override
    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        return self.before_model(state, runtime)
