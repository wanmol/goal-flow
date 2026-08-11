"""EntryGuardMiddleware: entry short-circuit middleware (replaces the ``AgentRuntime.before_call`` hook).

Design intent: push the common pattern "entry precheck fails → directly return a fixed reply" down
from a Runtime hook into a standalone LangChain ``AgentMiddleware``, so it can:

- Be reused across Agents (one predicate used on multiple Agents)
- Be imported, tested, and composed independently (with controllable ordering relative to other middleware)
- Stay stylistically consistent with the LangChain middleware ecosystem (``ContextMiddleware`` / ``SensitiveCheckMiddleware`` etc.)

Applicable scenarios:
- State precheck fails → directly return a fixed prompt
- User identity not authenticated → reject
- Business precondition not met → prompt the user to supply more information

**Not applicable** scenarios (keep using the ``before_call`` hook):
- Need ``Command(goto="some_node")`` to jump to a specific node (this middleware can only ``jump_to=["end"]``)
- Need to ``update`` multiple state fields on short-circuit (the middleware only updates messages)

Correspondence with the ``before_call`` hook:

    # Old style (hook)
    def before_call(self, state):
        if not state.get("category"):
            return Command(update={"reply": "Please select a category first"})
        return None

    # New style (middleware)
    EntryGuardMiddleware(
        lambda state, runtime:
            ("end", "Please select a category first") if not state.get("category") else None
    )
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


# predicate returns (jump_to, reply_text) to trigger short-circuit; returns None to continue the normal flow
GuardResult = Optional[Tuple[str, str]]
GuardPredicate = Callable[[ContextAgentState, "Runtime[Any]"], GuardResult]


class EntryGuardMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """Entry short-circuit middleware.

    Pass ``predicate(state, runtime) -> (jump_to, reply) | None`` at construction:

    - returns ``None``: allow through, continue subsequent middleware / agent loop
    - returns ``("end", "fallback text")``: short-circuit to end, writing ``AIMessage(content="fallback text")``
      into messages as the final reply
    """

    def __init__(self, predicate: GuardPredicate):
        self._predicate = predicate

    @override
    @hook_config(can_jump_to=["end"])
    def before_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        result = self._predicate(state, runtime)
        if result is None:
            return None
        jump_to, reply = result
        return {"jump_to": jump_to, "messages": [AIMessage(content=reply)]}

    @override
    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)
