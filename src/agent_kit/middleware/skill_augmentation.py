"""SkillAugmentationMiddleware: splice skill details into the system prompt + route the skill tool.

Design intent: replaces the ad-hoc integration where ``AgentRuntime`` called ``SkillOrchestrator``
in the ``run()`` state machine. This middleware does two things:

1. ``@dynamic_prompt`` dimension: each round, match the most relevant skill details and splice them into the system prompt
2. ``wrap_tool_call`` dimension: track skill tool calls for metric / labeling (optional)

Business usage::

    from agent_kit import SkillOrchestrator, SkillAugmentationMiddleware

    orch = SkillOrchestrator.create_default("./skills")
    agent = Agent(
        middleware=[SkillAugmentationMiddleware(orch, match_top_k=3, match_threshold=0.3)],
        tools=orch.materialize_tools(...),  # convert executable skills into LangChain tools
        ...
    )

On a match error, **silently falls back to the original prompt** (so a skill failure doesn't drag down the main flow) -- consistent
with the existing fallback behavior of ``AgentRuntime.run()``.
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
from langchain_core.messages import SystemMessage
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

logger = logging.getLogger(__name__)


def _extract_query(request: ModelRequest) -> str:
    """Take the content of the most recent user message from the request as the skill match query."""
    from langchain_core.messages import HumanMessage

    messages = request.messages or []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        return str(block["text"])
                    if isinstance(block, str):
                        return block
            return str(content) if content else ""
    return ""


def _existing_system_prompt(request: ModelRequest) -> str:
    sm = request.system_message
    if sm is None:
        return ""
    if isinstance(sm, SystemMessage):
        content = sm.content
        return content if isinstance(content, str) else str(content)
    return str(sm)


class SkillAugmentationMiddleware(
    AgentMiddleware[ContextAgentState, ContextT, ResponseT]
):
    """Before each model call, splice the matched skill details into the system prompt.

    Constructor parameters:
    - ``orchestrator``: the ``SkillOrchestrator`` instance
    - ``match_top_k``: max number of skills matched per round (default 3)
    - ``match_threshold``: match confidence threshold (default 0.3)
    - ``query_extractor``: custom query extraction (defaults to taking the HumanMessage at the end of messages)
    """

    def __init__(
        self,
        orchestrator: Any,
        *,
        match_top_k: int = 3,
        match_threshold: float = 0.3,
        query_extractor: Optional[Callable[[ModelRequest], str]] = None,
    ):
        self._orchestrator = orchestrator
        self._top_k = match_top_k
        self._threshold = match_threshold
        self._query_extractor = query_extractor or _extract_query

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        try:
            query = self._query_extractor(request)
            if not query:
                return handler(request)
            base_prompt = _existing_system_prompt(request)
            augmented = self._orchestrator.match_and_augment(
                query=query,
                base_prompt=base_prompt,
                top_k=self._top_k,
                threshold=self._threshold,
            )
            if augmented and augmented != base_prompt:
                request = request.override(system_message=SystemMessage(content=augmented))
        except Exception as e:
            logger.warning(
                f"SkillAugmentationMiddleware: augmentation failed, "
                f"continuing with base prompt: {e}"
            )
        return handler(request)
