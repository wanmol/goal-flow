"""
DeepAgentRuntime: an AgentRuntime implementation based on deepagents.create_deep_agent.

After inheriting AgentRuntime, you only need to implement:
- _build_graph(): call create_deep_agent + assemble the 4 advanced hooks (subagents/memory/interrupt_on/response_format)
- _execute_graph(): run graph.stream + extract raw_messages / todos / reply

The 4 advanced hooks unique to deepagents (subagents / memory / interrupt_on / response_format)
are exposed as DeepAgentRuntime's extension interface, overridden by business subclasses as needed.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from agent_kit.runtimes.base import AgentRuntime, ResultT


logger = logging.getLogger(__name__)


class DeepAgentRuntime(AgentRuntime[ResultT]):
    """The Runtime for the deepagents form.

    On top of AgentRuntime's 12 shared hooks, additionally exposes 4 advanced hooks unique to deepagents:
    - build_subagents(): concurrent Sub-agents
    - memory_keys(): AGENTS.md paths loaded into the prompt at startup
    - interrupt_on_tools(): HITL interrupt before a tool call
    - response_format(): structured response format

    All return empty by default, overridden by business subclasses as needed.
    """

    # ───── 4 advanced hooks unique to deepagents ──────────────

    def build_subagents(self) -> list:
        """Return the deepagents subagents list (SubAgent / CompiledSubAgent / AsyncSubAgent)."""
        return []

    def memory_keys(self) -> list[str]:
        """Return the list of AGENTS.md paths to load into the system prompt at startup."""
        return []

    def interrupt_on_tools(self) -> dict:
        """Return the mapping of tool names requiring HITL interrupt (dict[tool_name, InterruptOnConfig | bool])."""
        return {}

    def response_format(self):
        """Return the structured response format (Pydantic class / TypedDict / dict schema), default None."""
        return None

    # ───── _build_graph: delegates to DeepGraphBuilder (P4, ADR-003) ─────

    def _build_graph(self, *, state=None, system_prompt: str = "", user_content: str = ""):
        """Delegate graph assembly to ``DeepGraphBuilder``.

        P4 (ADR-003): this method no longer directly calls ``deepagents.create_deep_agent``, instead
        going through the ``DeepGraphBuilder`` strategy object. The ``Runtime``-specific 4 hooks
        (``build_subagents`` / ``memory_keys`` / ``interrupt_on_tools`` /
        ``response_format``) are injected when constructing the Builder.

        The new ``Agent`` class's graph assembly goes through the same ``DeepGraphBuilder`` -- this eliminates
        the double maintenance cost of two scheduling paths (AgentRuntime / Agent) over the underlying graph API.
        """
        from agent_kit.graphs.deep import DeepGraphBuilder

        subagents = self.build_subagents() or []
        memory = self.memory_keys() or []
        interrupt_on = self.interrupt_on_tools() or {}
        rf = self.response_format()

        builder = DeepGraphBuilder(
            subagents=subagents,
            memory=memory,
            interrupt_on=interrupt_on,
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
            f"{type(self).__name__}: deepagents graph created via DeepGraphBuilder "
            f"(subagents={len(subagents)}, memory_keys={len(memory)}, "
            f"interrupt_on={list(interrupt_on.keys())}, "
            f"response_format={'yes' if rf else 'no'}),"
            f"middleware_extra={self.middleware_extra()}"
                   )
        return graph

    # ───── _execute_graph implementation: streaming + extract result ─────────

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
        ctx_fields["sys_conversation_id"] = state.get("sys_conversation_id","")
        ctx = self._build_context(ctx_fields)

        out, streamed_any = self._stream_agent_messages(
            graph=graph,
            input_msg={"messages": [HumanMessage(content=user_content)]},
            ctx=ctx,
            thread_id=thread_id,
        )

        all_messages = out.get("messages") or []
        result.raw_messages = list(all_messages)
        result.extra["todos"] = list(out.get("todos") or [])
        result.reply = self._extract_last_reply(all_messages)

        if result.reply and not streamed_any:
            self._stream_callback(result.reply)
