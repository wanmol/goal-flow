"""
StateGraphRuntime: an AgentRuntime implementation based on a manual StateGraph.

Positioning: a fully custom state machine (multi-step, multi-branch, multi-LLM-call), where the subclass assembles the graph itself.
Suitable for: bargaining nodes (Tit-for-Tat multiple rounds), review pipelines (decompose → parallel evaluation → aggregate), etc.

Subclasses must implement one additional hook:
- build_state_graph(*, state=None, system_prompt="", user_content="") -> StateGraph
  Return an uncompiled langgraph.graph.StateGraph

StateGraphRuntime is responsible for:
- compiling the graph and assembling the checkpointer
- streaming drive + extract reply (per the state key agreed by the subclass)
- sharing the same AgentRuntime protocol with other Runtimes (hooks, make_tool, error classification)

State Key convention:
- The StateGraph's input/output must contain ``messages: list`` (consistent with mainstream langgraph convention)
- The content of the last AI message serves as result.reply
- Subclasses with special data can stuff it into result.extra via the ``state_to_extra(out_state)`` hook
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage

from agent_kit.runtimes.base import AgentRuntime, ResultT


logger = logging.getLogger(__name__)


class StateGraphRuntime(AgentRuntime[ResultT]):
    """The Runtime for the manual StateGraph form.

    More flexible than DeepAgent / CreateAgent -- the subclass fully controls the state machine;
    but also has the most boilerplate -- the subclass must define the state schema, node functions, and edges itself.

    StateGraphRuntime only handles:
    - checkpointer assembly + thread_id isolation
    - streaming token pass-through
    - reply / raw_messages extraction
    - error classification + metric/stream callback injection (inherited from AgentRuntime)
    """

    @abstractmethod
    def build_state_graph(
        self,
        *,
        state: Any = None,
        system_prompt: str = "",
        user_content: str = "",
    ):
        """Construct and return an uncompiled ``langgraph.graph.StateGraph``.

        ``state/system_prompt/user_content`` are only passed through by the Runtime when
        ``cache_graph=False``; in cache mode they are placeholder empty values (None / ""). If the subclass
        does not depend on per-turn info, it can ignore these three parameters.
        """

    def state_to_extra(self, out_state: dict) -> dict:
        """Translate the graph's final-state dict into result.extra (default empty)."""
        return {}

    def _build_graph(
        self,
        *,
        state: Any = None,
        system_prompt: str = "",
        user_content: str = "",
    ):
        from langgraph.checkpoint.memory import InMemorySaver

        g = self.build_state_graph(
            state=state,
            system_prompt=system_prompt,
            user_content=user_content,
        )
        graph = g.compile(checkpointer=InMemorySaver())
        logger.info(
            f"{type(self).__name__}: state_graph compiled (nodes={list(g.nodes)})"
        )
        return graph

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
        input_msg = {
            "messages": [HumanMessage(content=user_content)],
            "system_prompt": system_prompt,
            "user_content": user_content,
        }

        out, _streamed_any = self._stream_agent_messages(
            graph=graph,
            input_msg=input_msg,
            ctx=None,  # StateGraph has no context_schema
            thread_id=thread_id,
        )

        all_messages = out.get("messages") or []
        result.raw_messages = list(all_messages)

        try:
            extra = self.state_to_extra(out) or {}
            result.extra.update(extra)
        except Exception as e:
            logger.warning(f"{type(self).__name__}: state_to_extra failed: {e}")

        result.reply = self._extract_last_reply(all_messages)
