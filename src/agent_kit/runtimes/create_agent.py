"""
CreateAgentRuntime: an AgentRuntime implementation based on langchain.agents.create_agent.

Positioning: a minimal tool-calling Agent, without deepagents' planning/subagents/memory/todos complexity.
Suitable for: single-goal small nodes (classification, extraction, rewriting, compliance review, simple QA, etc.).

Underlying API choice: langchain.agents.create_agent (the official recommendation in langchain 0.3+),
same lineage as deepagents -- deepagents.create_deep_agent is internally also built on create_agent.

Advanced hook: exposes response_format(), corresponding to create_agent(response_format=...).
Other middleware goes uniformly through middleware_extra().
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from agent_kit.runtimes.base import AgentRuntime, ResultT


logger = logging.getLogger(__name__)


class CreateAgentRuntime(AgentRuntime[ResultT]):
    """The Runtime for the langchain.agents.create_agent form.

    Shares 80% of the pattern with DeepAgentRuntime (dynamic_prompt + context_schema + checkpointer +
    streaming + extract reply); the only difference is it does not pass deepagents-specialized subagents/memory/interrupt_on/todos.

    Advanced hooks exposed:
    - response_format(): structured response (same-named API as DeepAgentRuntime)
    """

    # ───── Advanced hooks ──────────────────────────────────

    def response_format(self):
        """Return the structured response format (Pydantic class / TypedDict / dict schema), default None."""
        return None

    # ───── _build_graph: delegates to ReactGraphBuilder (P4, ADR-003) ────

    def _build_graph(self, *, state=None, system_prompt: str = "", user_content: str = ""):
        """Delegate graph assembly to ``ReactGraphBuilder``.

        P4 (ADR-003): this method no longer directly calls ``langchain.agents.create_agent``, instead
        going through the ``ReactGraphBuilder`` strategy object. The ``Runtime``-specific ``response_format()``
        is injected when constructing the Builder, while runtime-layer ``model`` / ``tools`` / ``middleware`` /
        ``context_schema`` are passed in at ``build()`` time.

        The new ``Agent`` class's graph assembly goes through the same ``ReactGraphBuilder`` -- this eliminates
        the double maintenance cost of two scheduling paths (AgentRuntime / Agent) over the underlying graph API.
        """
        from agent_kit.graphs.react import ReactGraphBuilder

        rf = self.response_format()
        builder = ReactGraphBuilder(
            response_format=rf,
            context_schema=self._build_context_schema(),
        )
        graph = builder.build(
            model=self._get_llm(),
            tools=self._collect_all_tools(),
            middleware=[
                self._dynamic_system_prompt_middleware(),
                *self.middleware_extra(),
            ],
        )
        logger.info(
            f"{type(self).__name__}: create_agent graph created via ReactGraphBuilder "
            f"(response_format={'yes' if rf else 'no'})"
        )
        return graph

    # ───── _execute_graph: streaming + extract result ──────────────

    def _execute_graph(
        self,
        *,
        graph: Any,
        state: Any,
        system_prompt: str,
        user_content: str,
        thread_id: str,
        result: ResultT,
    ) -> None:
        ctx_fields = dict(self.context_extra_fields(state) or {})
        ctx_fields["system_prompt"] = system_prompt
        ctx = self._build_context(ctx_fields)

        out, _streamed_any = self._stream_agent_messages(
            graph=graph,
            input_msg={"messages": [HumanMessage(content=user_content)]},
            ctx=ctx,
            thread_id=thread_id,
        )

        all_messages = out.get("messages") or []
        result.raw_messages = list(all_messages)

        if "structured_response" in out:
            result.extra["structured_response"] = out["structured_response"]

        result.reply = self._extract_last_reply(all_messages)
