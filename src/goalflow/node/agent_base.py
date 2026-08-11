"""``node/agent_base``: the next-generation base class for workflow nodes.

Based on the ADR-003 ``agent_kit.Agent`` + ``GraphBuilder`` strategy, replacing the old:

- ``node/deep_agent_base.py::DeepAgentBaseNode``
- ``node/create_agent_base.py::CreateAgentBaseNode``
- ``node/state_graph_base.py::StateGraphBaseNode``

The old 3 bases still work (marked with ``DeprecationWarning``), business nodes need no changes; new nodes should inherit this class.

Design points (ADR-004):

- **Single base class, graph shape parameterized**: switch between
  ``ReactGraphBuilder`` (default) / ``DeepGraphBuilder`` / ``CustomGraphBuilder`` via ``build_graph_builder_for_agent()``
- **Hooks from 12 → 4**: business subclasses only implement ``output_schema`` / ``build_prompt`` /
  ``serialize_output`` / [optional] ``format_user_input``; everything else goes through LangChain
  ``AgentMiddleware``
- **workflow bridge**: ``BaseNode.call(state) → Agent.run(state, sys_query)``;
  ``stream_callback`` is injected via ``RunnableConfig.configurable["stream_callback"]``
  (avoiding implicit ContextVar state)
- **Harness sharing**: defaults to ``default_harness()``, sharing the ``HARNESS_*`` singletons with the old API

Minimal usage::

    from goalflow.node.agent_base import AgentBaseNode
    from pydantic import BaseModel
    from langgraph.types import Command

    class MyOutput(BaseModel):
        reply: str = ""
        label: str = ""

    class CategoryClassifyNode(AgentBaseNode[MyOutput]):
        name = "category_classify"  # also the task_type for harness.router.get

        def output_schema(self): return MyOutput
        def build_prompt(self, state): return "You are an enterprise service category classifier."
        def serialize_output(self, state, output):
            if isinstance(output, MyOutput):
                return Command(update={"reply": output.reply, "label": output.label})
            return Command(update={"reply": str(output)})

Switching the underlying graph shape::

    from agent_kit import DeepGraphBuilder

    class MyDeepAgent(AgentBaseNode[MyOutput]):
        name = "deep_collector"
        def build_graph_builder_for_agent(self):
            return DeepGraphBuilder(memory=["./AGENTS.md"])
        ...
"""
from __future__ import annotations

import contextvars
from abc import abstractmethod
from typing import Any, ClassVar, Generic, Optional, Sequence, TypeVar

from langchain.agents.middleware import AgentMiddleware
from langgraph.types import Command
from langgraph.config import get_stream_writer
from pydantic import BaseModel

from agent_kit import Agent, default_harness, ConversationHistoryMiddleware
from agent_kit.graphs import GraphBuilder

from goalflow.config import get_logger
from goalflow.node._harness_bootstrap import ensure_harness_wired
from goalflow.node.base import BaseNode
from goalflow.state import GenericState
from goalflow.workflow.stream.types import CUSTOM_STREAM_MODE_DIRECT_OUTPUT

logger = get_logger(__name__)

OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentBaseNode(BaseNode, Agent[OutputT], Generic[OutputT]):
    """workflow node + ``agent_kit.Agent`` combination (ADR-004, replaces the old 3 ``*BaseNode``).

    Business subclasses must implement:

    - ``output_schema() -> type[BaseModel]`` (``Agent`` abstract)
    - ``build_prompt(state) -> str`` (``Agent`` abstract)
    - ``build_command(state, output) -> Command`` (**abstract in this class**: translates the Agent
      product into a LangGraph ``Command``, deciding workflow routing / state updates)

    Optional overrides (defaults are reasonable):

    - ``format_user_input(state, query) -> str`` (``Agent`` optional): passes the query through by default
    - ``format_output(state, output) -> Any`` (``Agent`` optional): passes the graph output through by default;
      subclasses that want typed parsing / post-processing override this

    Switch the underlying graph shape via ``build_graph_builder_for_agent()``:

    - default ``ReactGraphBuilder`` (replaces the old ``CreateAgentBaseNode``)
    - ``DeepGraphBuilder`` (replaces the old ``DeepAgentBaseNode``)
    - ``CustomGraphBuilder`` (replaces the old ``StateGraphBaseNode``)

    The 5 optional factory hooks (by class hierarchy):

    - ``build_tools_for_agent() -> list``
    - ``build_middleware_for_agent() -> list``
    - ``build_graph_builder_for_agent() -> Optional[GraphBuilder]``
    - ``build_harness_for_agent() -> Optional[Harness]``
    - ``cache_graph: bool`` (class attribute, defaults to True)

    **Separation of responsibilities**:

    - ``Agent.format_output``: workflow-agnostic, does typed parsing / field extraction
    - ``AgentBaseNode.build_command``: workflow routing / state updates / goto decisions

    ``call()`` internal chain: ``Agent.run`` → ``format_output`` → ``build_command`` → ``Command``.

    Concurrency convention: instances cannot be reused concurrently; the workflow engine guarantees the same node runs serially.
    turn-internal state is passed via LangGraph state rather than instance attributes.
    """

    name: str = "agent_node"
    """Agent identifier. Also serves as the task_type for ``harness.router.get(name)``,
    the prefix for ``MetricsMiddleware``, the langfuse span name, etc."""

    cache_graph: bool = True
    """Whether to cache the compiled product. Set False for scenarios needing per-turn topology, such as negotiation / Tit-for-Tat."""

    # ── Concurrency safety: ``_reply_streamed`` uses a ContextVar ────────────────────
    #
    # Node instances are **process-level singletons** in the workflow engine -- the same instance may be
    # run concurrently by multiple asyncio tasks / threads (same node across different sessions). Use a
    # ``ContextVar`` rather than an instance attribute for per-request isolation:
    #
    # - ``call()`` entry ``set(False)`` gets a token; finally ``reset(token)`` guarantees returning to
    #   the outer context's state after exit (also safe on the exception path)
    # - ``stream_text`` / ``_stream_callback`` call ``set(True)`` to write the current context
    # - business code reads via ``self._reply_streamed`` (property forwards ContextVar.get)
    #   or writes via ``self._reply_streamed = True / False`` (setter forwards ContextVar.set)
    #
    # A ContextVar is independent within each asyncio task → concurrent call() do not interfere with each other.
    _reply_streamed_var: ClassVar[contextvars.ContextVar[bool]] = contextvars.ContextVar(
        "agent_base_node_reply_streamed", default=False,
    )

    @property
    def _reply_streamed(self) -> bool:
        """Whether text has already been streamed within this call(). Reads the ContextVar, per-request isolated."""
        return self._reply_streamed_var.get()

    @_reply_streamed.setter
    def _reply_streamed(self, value: bool) -> None:
        """Supports the business-code ``self._reply_streamed = True/False`` style.

        ``call()`` already does full lifecycle management with ``set(False)`` + ``reset(token)``;
        this setter is only for turn-internal local modifications (such as ``stream_text`` / fallback branches).
        """
        self._reply_streamed_var.set(value)

    def __init__(self, *, llm: Optional[Any] = None, **kwargs):
        # Initialize BaseNode first (accepts workflow node config fields such as desc/title/type/...)
        BaseNode.__init__(self, **kwargs)

        # Ensure the LLM factory / metrics / langfuse are wired into HARNESS_* (idempotent)
        ensure_harness_wired()

        # Business may return a tuple/Sequence; normalize to a list before checking existence
        middleware = list(self.build_middleware_for_agent() or [])
        # Only inject the default when business does not explicitly provide a ConversationHistoryMiddleware
        # (when business wants custom config such as save_turn=True, its own instance takes priority)
        if not any(isinstance(m, ConversationHistoryMiddleware) for m in middleware):
            middleware.insert(0, ConversationHistoryMiddleware(save_turn=False))

        # Then initialize Agent (accepts model/tools/middleware/graph_builder/harness/...)
        Agent.__init__(
            self,
            model=llm,
            tools=self.build_tools_for_agent(),
            middleware=middleware,
            graph_builder=self.build_graph_builder_for_agent(),
            harness=self.build_harness_for_agent(),
            cache_graph=self.cache_graph,
        )
        # No longer using the self._reply_streamed = False instance attribute -- the ContextVar property above takes over

    # ───── The 5 optional hooks (with default fallbacks) ──────────────────────

    def build_tools_for_agent(self) -> Sequence[Any]:
        """Business tools. Empty by default."""
        return []

    def build_middleware_for_agent(self) -> Sequence[AgentMiddleware]:
        """The LangChain ``AgentMiddleware`` chain. Empty by default.

        Typical business setup:

            from agent_kit import (
                EntryGuardMiddleware,
                FallbackReplyMiddleware,
                ConversationHistoryMiddleware,
                MetricsMiddleware,
            )

            def build_middleware_for_agent(self):
                return [
                    EntryGuardMiddleware(self._check_entry),
                    FallbackReplyMiddleware(fallback_reply="..."),
                    ConversationHistoryMiddleware(save_turn=True),
                    MetricsMiddleware(default_harness(), prefix=self.name),
                ]
        """
        return []

    def build_graph_builder_for_agent(self) -> Optional[GraphBuilder]:
        """Select the underlying graph shape. Returning ``None`` uses the ``Agent`` default (``ReactGraphBuilder``).

        - return ``ReactGraphBuilder(...)``: equivalent to the old ``CreateAgentBaseNode``
        - return ``DeepGraphBuilder(...)``: equivalent to the old ``DeepAgentBaseNode``
        - return ``CustomGraphBuilder(fn)``: equivalent to the old ``StateGraphBaseNode``
        """
        return None

    def build_harness_for_agent(self):
        """Return a ``Harness`` instance; defaults to ``default_harness()`` sharing state with the global HARNESS_*.

        In unit tests business can return an independent instance built with ``Harness()`` for isolation.
        """
        return default_harness()

    # ───── Abstract hook: build_command (translate the Agent product into a Command) ──────────

    @abstractmethod
    def build_command(self, state: GenericState, output: Any) -> Command:
        """Translate the product returned by ``Agent.run`` (processed by ``format_output``) into a
        LangGraph ``Command``.

        This method is the workflow layer's "routing + state update" decision point. The shape of ``output``
        is determined by ``format_output``:

        - default (``format_output`` not overridden): ``output`` is a ``str`` (the AI text at the end of
          messages) or an ``output_schema()`` instance (when structured_response hits)
        - subclass overrides ``format_output``: ``output`` can be any type

        Typical implementation::

            def build_command(self, state, output):
                if isinstance(output, MyOutput):
                    return Command(
                        update={"reply": output.reply, "label": output.label},
                        goto=["next_node"],
                    )
                return Command(update={"reply": str(output)})

        ``Agent`` itself is workflow-agnostic -- ``Command`` is a LangGraph-framework-specific output, so
        ``AgentBaseNode`` (the workflow adaptation layer) holds this abstraction.
        """

    # ───── stream_text: bridge to LangGraph SSE ──────────────

    def stream_text(self, text: str) -> None:
        """Workflow node streaming output. Pushes to SSE via the LangGraph custom stream writer.

        Consistent with the old ``WorkflowAgentNodeMixin.stream_text`` behavior, making it convenient for
        business nodes to actively push text outside of ``serialize_output``.
        """
        if text:
            # Go directly through ContextVar.set to avoid the property redirection overhead
            self._reply_streamed_var.set(True)
        if not text:
            return

        writer = get_stream_writer()

        try:
            writer((CUSTOM_STREAM_MODE_DIRECT_OUTPUT, {"node_id": self.id, "text": text}))
        except Exception as e:
            logger.error(
                f"{type(self).__name__}.stream_text failed. node_id={self.id} error={e}",
                exc_info=True,
            )

    # ───── BaseNode.call → Agent.run → build_command bridge ────────────────

    def call(self, state: GenericState, config: Optional[dict] = None) -> Command:
        """Workflow call entry point.

        Flow:

        1. The ContextVar set/reset(token) pattern locks this turn's ``_reply_streamed`` isolation
        2. Get the user query from ``state["sys_query"]``
        3. Construct ``_stream_callback``, inject it into ``RunnableConfig.configurable["stream_callback"]``,
           so that ``Agent.run`` streams natively (``graph.stream(stream_mode='messages')``), calling the
           callback once per AIMessageChunk text
        4. Call ``Agent.run(state, user_query, config=run_config)`` to get the product processed by
           ``format_output`` (passed through by default = ``str`` or ``output_schema`` instance)
        5. Call ``self.build_command(state, output)`` to translate the product into a ``Command`` and return it
        """
        user_query = state.get("sys_query", "") if hasattr(state, "get") else ""

        # set/reset(token): force initialization to False within this ctx; on call() exit
        # (normal return / exception) roll back to the outer context's value, avoiding dirty state leaking into the next request
        token = self._reply_streamed_var.set(False)
        try:
            def _stream_callback(token_text: str) -> None:
                if token_text:
                    self._reply_streamed_var.set(True)
                self.stream_text(token_text)

            run_config: dict = dict(config or {})
            configurable = dict(run_config.get("configurable") or {})
            configurable.setdefault("stream_callback", _stream_callback)
            run_config["configurable"] = configurable

            # Agent.run → the product processed by format_output (passed through by default)
            output = self.run(state, user_query, config=run_config)
            # Workflow layer: translate the product into a LangGraph Command
            return self.build_command(state, output)
        finally:
            self._reply_streamed_var.reset(token)


__all__ = ["AgentBaseNode"]
