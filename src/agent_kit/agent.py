"""Agent: the new public entry point (replaces ``AgentRuntime``).

Design intent (ADR-003):
- Compress ``AgentRuntime``'s 12 hooks into 4 abstract + 2 optional
- All "aspects" (short-circuit, skip LLM, sensitive words, history, fallback, streaming, metrics, langfuse, skills)
  are plugged in externally via ``middleware=[...]``
- The three underlying graph APIs (``create_agent`` / ``create_deep_agent`` / custom graph)
  become ``GraphBuilder`` strategy objects, injected at construction time
- Governance dependencies (LLM routing / prompt registry / tracer / profiles) are injected
  explicitly via a ``Harness`` instance, no longer relying on global singletons

The legacy ``AgentRuntime`` remains usable (P2 already added a DeprecationWarning). The two API sets coexist.

Minimal usage (Agent itself is workflow-agnostic; ``run()`` returns the product of ``format_output``)::

    class MyAgent(Agent[MyOutput]):
        name = "my_classifier"

        def output_schema(self):
            return MyOutput

        def build_prompt(self, state):
            return "You are a classifier."

        # format_output passes through by default; override for typed parsing etc.
        # def format_output(self, state, output): return output

    agent = MyAgent(model="qwen-plus", tools=[my_tool])
    output = agent.run({}, "I'm looking for a tax planning firm")
    # output is a MyOutput instance (structured_response hit) or str (trailing messages text)

Workflow scenario (inherit ``node.agent_base.AgentBaseNode``)::

    class MyNode(AgentBaseNode[MyOutput]):
        name = "my_classifier"
        def output_schema(self): return MyOutput
        def build_prompt(self, state): return "You are a classifier."
        def build_command(self, state, output):
            return Command(update={"reply": output.reply, "label": output.label})
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, Sequence, TypeVar

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel

from agent_kit.middleware.subagent_middleware import SubAgentInitializeMiddleware

from agent_kit.graphs import (
    DeepGraphBuilder,
    ReactGraphBuilder,  
)

logger = logging.getLogger(__name__)


OutputT = TypeVar("OutputT", bound=BaseModel)


# Default thread_id -- business code usually supplies one via RunnableConfig
_DEFAULT_THREAD_ID = "agent_default"


def _extract_text(content: Any) -> str:
    """Normalize message content to a plain str (tolerating list-of-dict form)."""
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


def _extract_last_reply(messages: list) -> str:
    """Find the last non-tool_call AI text from the tail of the message stream as the reply."""
    for m in reversed(messages or []):
        if isinstance(m, AIMessage):
            if getattr(m, "tool_calls", None) and not m.content:
                continue
            text = _extract_text(m.content)
            if text:
                return text.strip()
    return ""

from deepagents.middleware.subagents import (
    CompiledSubAgent,
    SubAgent,
)
from deepagents.middleware.async_subagents import AsyncSubAgent

# AsyncSubAgent and CompiledSubAgent are not supported; currently only SubAgent supports middleware, and subagents need to initialize context-isolation via middleware
_SubAgentType = SubAgent 
#_SubAgentType = SubAgent | CompiledSubAgent | AsyncSubAgent


class Agent(ABC, Generic[OutputT]):
    """Unified Agent entry point (workflow-agnostic).

    Subclasses must implement:
    - ``output_schema() -> type[BaseModel]``: declare the structured output shape
    - ``build_prompt(state) -> str``: construct the system prompt

    Optional overrides:
    - ``format_user_input(state, query) -> str``: customize the user message body; passes ``query`` through by default
    - ``format_output(state, output) -> Any``: format the graph's raw output; passes through by default

    Translating "to a Command / dict / other framework-specific output" is left to the
    workflow adaptation layer (e.g. ``node.agent_base.AgentBaseNode.build_command``), keeping
    the Agent itself independently testable and usable outside workflow scenarios.

    All "aspect" behaviors (short-circuit, skip, fallback, streaming, metrics, history, sensitive words, skills)
    are injected via ``middleware=[...]`` rather than being hooks.
    """

    name: str = "agent"
    """Agent identifier; also serves as the task_type for ``harness.router.get(name)``, metric prefix, etc."""

    def __init__(
        self,
        *,
        model: Optional[Any] = None,
        tools: Sequence[Any] = (),
        subagents: Sequence[_SubAgentType] | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        graph_builder: Optional[Any] = None,
        harness: Optional[Any] = None,
        cache_graph: bool = True,
    ):
        """Construct an Agent instance.

        :param model: LLM instance / model-name string / None.
            - ``None`` and ``harness`` provided: fetched from ``harness.router.get(self.name)``
            - ``str``: instantiated via ``langchain.chat_models.init_chat_model``
            - otherwise: used directly as a ``BaseChatModel``
        :param tools: business tools (``BaseTool`` instances)
        :param middleware: middleware chain; execution order follows list order
        :param graph_builder: ``GraphBuilder`` instance; defaults to ``ReactGraphBuilder()``
        :param harness: ``Harness`` instance; used for LLM routing + governance capability injection
        :param cache_graph: whether to reuse the compiled product. When ``True``, the graph is built only once
        """
        self._model = model
        self._tools = list(tools)
        self._middleware = list(middleware)
        self._graph_builder = graph_builder
        self._harness = harness
        self._cache_graph = cache_graph
        self._compiled: Optional[Any] = None
        self._subagents = list(subagents or [])

    # ───── The 3 abstract hooks subclasses must implement ───────────────────

    @abstractmethod
    def output_schema(self) -> type[OutputT]:
        """Declare this Agent's structured output shape. ``ReactGraphBuilder`` /
        ``DeepGraphBuilder`` pass this schema to the ``response_format`` parameter.
        """

    @abstractmethod
    def build_prompt(self, state: Any) -> str:
        """Construct the system prompt. Called once per run."""

    # ───── Optional overrides (default implementation passes through) ─────────────────

    def format_user_input(self, state: Any, query: str) -> str:
        """Format user input into the message content sent to the LLM. Passes through by default."""
        return query

    def format_output(self, state: Any, output: Any) -> Any:
        """Format the graph's raw output. Passes through by default -- returns ``output`` as-is.

        ``output`` may be:
        - an instance of ``output_schema()`` (if the graph enabled structured_response)
        - a plain string (the last AI text reply)

        Subclasses may override to do typed parsing, field extraction, post-processing, etc.

        **Translating "to a Command" is no longer the Agent's responsibility** -- the workflow layer
        (e.g. ``AgentBaseNode.build_command``) is responsible for translating the ``format_output``
        product into framework-specific output (``Command`` / ``dict`` / other). The Agent itself
        stays workflow-agnostic.
        """
        return output

    # ───── Internal: model / graph resolution ──────────────────────

    def _resolve_model(self) -> Any:
        """Tri-state model resolution: directly passed > model string > harness.router.get(name)."""
        if self._model is not None and not isinstance(self._model, str):
            return self._model
        if isinstance(self._model, str):
            try:
                from langchain.chat_models import init_chat_model

                return init_chat_model(self._model)
            except Exception as e:
                raise RuntimeError(
                    f"Agent {self.name!r}: failed to init_chat_model({self._model!r}): {e}"
                )
        if self._harness is not None:
            router = getattr(self._harness, "router", None)
            if router is None:
                raise RuntimeError(
                    f"Agent {self.name!r}: harness.router missing"
                )
            return router.get(self.name)
        raise RuntimeError(
            f"Agent {self.name!r}: no model resolved "
            f"(pass model=... or harness=Harness(...))"
        )

    def _resolve_graph_builder(self) -> Any:
        if self._graph_builder is not None:
            return self._graph_builder
        
        # If there are subagents, force DeepGraphBuilder (only deepagent supports subagents)
        if self._subagents:
            for subagent in self._subagents:
                if not isinstance(subagent, _SubAgentType):
                    raise ValueError(
                        f"Agent {self.name!r}: subagents must be _SubAgentType instances"
                    )
                
                sub_middleware = subagent.get("middleware", [])
                # Insert SubAgentInitializeMiddleware at the front of middleware to initialize the subagent's messages parameter
                sub_middleware.insert(0, SubAgentInitializeMiddleware())
                subagent["middleware"] = sub_middleware
                
            return DeepGraphBuilder(
                subagents=self._subagents,
            )
    
        # Default ReactGraphBuilder (most common)
        return ReactGraphBuilder()

    def _compile(self) -> Any:
        """Compile the graph; reuse depends on ``cache_graph``."""
        if self._cache_graph and self._compiled is not None:
            return self._compiled
        builder = self._resolve_graph_builder()
        graph = builder.build(
            model=self._resolve_model(),
            tools=self._tools,
            middleware=list(self._middleware),
            output_schema=self.output_schema(),
        )
        if self._cache_graph:
            self._compiled = graph
        return graph

    def invalidate_graph(self) -> None:
        """Manually clear the compile cache; rebuild on the next ``_compile``."""
        self._compiled = None

    # ───── Execution entry point ──────────────────────────────────────

    def run(
        self,
        state: Any,
        user_query: str,
        *,
        config: Optional[dict] = None,
    ) -> Any:
        """Execute one agent call. Returns the ``format_output`` product (passes graph output through by default).

        Execution flow:
        1. ``build_prompt(state)`` constructs the system prompt (middleware may override)
        2. ``format_user_input(state, user_query)`` constructs the user message body
        3. ``_compile()`` obtains the CompiledGraph
        4. **``graph.stream(stream_mode='messages')`` drives it chunk by chunk** -- each
           ``AIMessageChunk``'s text content is pushed via ``RunnableConfig.configurable["stream_callback"]``
           (business code injects it automatically via ``AgentBaseNode`` or sets it explicitly in ``config``)
        5. After the stream ends, ``graph.get_state(config).values`` gets the final state
        6. ``format_output(state, output)`` returns the final product

        Return value shapes:
        - default: ``str`` (trailing AI reply in messages) or an instance of ``output_schema()``
        - ``format_output`` overridden: decided by the subclass

        The responsibility of "translating to Command/dict or other framework-specific output" is
        left to the workflow layer (e.g. ``AgentBaseNode.build_command``); the Agent itself stays
        workflow-agnostic.
        """
        graph = self._compile()
        system_prompt = self.build_prompt(state)
        user_content = self.format_user_input(state, user_query)

        # Stash system_prompt into the RunnableConfig context (ReactGraphBuilder
        # expects to read it from runtime.context.system_prompt, matching the DynamicPromptMiddleware protocol)
        run_config: dict = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        # Compatible with the legacy thread_id concept (required by the LangGraph checkpointer)
        configurable.setdefault("thread_id", f"{self.name}__{_DEFAULT_THREAD_ID}")
        run_config["configurable"] = configurable

        input_state = {
            "messages": [HumanMessage(content=user_content)],
            # Put system_prompt into state too, for middleware (e.g. DynamicPromptMiddleware)
            "system_prompt": system_prompt,
        }
        if hasattr(state, "get"):
            for k in ("sys_conversation_id", "sys_user_id"):
                v = state.get(k)
                if v is not None:
                    input_state[k] = v

        # Streaming dispatch: push each AIMessageChunk to stream_callback (optional for business code)
        stream_callback = configurable.get("stream_callback")
        for chunk, _ in graph.stream(
            input_state, config=run_config, stream_mode="messages"
        ):
            if stream_callback is None or not isinstance(chunk, AIMessageChunk):
                continue
            chunk : AIMessageChunk = chunk
            response_metadata : dict = chunk.response_metadata
            # Skip pure tool_call chunks (no text content)
            if chunk.tool_call_chunks and not chunk.content:
                continue
            token = _extract_text(chunk.content)
            if not token:
                continue
            try:
                stream_callback(token)
            except Exception as e:
                logger.warning(
                    f"Agent.run: stream_callback raised: {e}",
                )

        # Get the final state after the stream ends
        result_state = graph.get_state(run_config).values

        # Prefer structured_response; otherwise use the trailing AI reply in messages
        output = result_state.get("structured_response")
        if output is None:
            output = _extract_last_reply(result_state.get("messages") or [])
        return self.format_output(state, output)
