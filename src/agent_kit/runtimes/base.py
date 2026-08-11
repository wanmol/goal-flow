"""
AgentRuntime: unified runtime base class shared across Agent forms.

Design intent:
- All Agent forms (DeepAgent / ReAct / custom StateGraph, etc.) inherit this base class
- Shared: hook skeleton, make_tool, run() state machine, error classification, metric/stream callback injection
- Each Runtime subclass only needs to implement two low-level hooks:
  - ``_build_graph()``: construct the concrete LangGraph instance for this form
  - ``_execute_graph(...)``: run the graph once + collect the result

Upward integration with Harness (Day3-7): the HarnessBacked mixin overrides _get_llm / build_system_prompt /
build_tools to connect any AgentRuntime to the Model Router / Prompt Registry / Skill Adapter.

Does not depend on:
- Any workflow engine types (BaseNode, etc.)
- Any specific repo's metric / LLM factory
- Langfuse (optional, imported on demand by Runtime subclasses)
"""
from __future__ import annotations

import contextvars
import functools
import logging
import time
import warnings
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, Optional, TypeVar

from langgraph.types import Command
from pydantic import BaseModel, Field

from agent_kit.runtimes.external_errors import reraise_if_critical

logger = logging.getLogger(__name__)


# P2 (ADR-002): the hooks below are now covered by their corresponding LangChain Middleware; overriding them emits a DeprecationWarning.
# They will be removed from the base class in P3 (next minor).
_DEPRECATED_HOOK_REPLACEMENTS: dict[str, str] = {
    "before_call": "EntryGuardMiddleware",
    "should_run_agent": "ModelSkipMiddleware",
    "on_failure": "FallbackReplyMiddleware",
}


# ---------------------------------------------------------------------------
# Result base class
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    """Unified base class for all Agent run results.

    Business subclasses inherit and add business fields. Runtime-specific extra info
    (such as DeepAgent's todos) goes into the ``extra`` dict, avoiding subclasses
    using isinstance to distinguish Runtime types.
    """

    reply: str = ""
    """The final text reply the Agent produces for the user."""

    failed: bool = False
    """Overall Agent failure flag."""

    raw_messages: list = Field(default_factory=list)
    """The full messages list from the graph state after the Agent runs."""

    extra: dict = Field(default_factory=dict)
    """Runtime-specific data (such as ``extra['todos']`` for DeepAgent)."""


ResultT = TypeVar("ResultT", bound=AgentResult)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def classify_error(error_text: str) -> str:
    """Classify an LLM/Agent exception into a metric label: compliance / tool_json / network / other."""
    if not error_text:
        return "other"
    t = error_text.lower()
    if any(
        k in t
        for k in (
            "inappropriate", "policy", "violat", "datainspectionfailed",
            "内容违规", "合规", "敏感",
        )
    ):
        return "compliance"
    if "function.arguments" in error_text or "json" in t or ("tool" in t and "arguments" in t):
        return "tool_json"
    if "timeout" in t or "connection" in t or "network" in t or "refused" in t:
        return "network"
    return "other"


# Callback type aliases
StreamCallback = Callable[[str], None]
MetricEmitter = Callable[..., None]


def extract_chunk_text(content: Any) -> str:
    """Normalize AIMessageChunk.content to a plain string for streaming.

    Different LangChain providers return content in varying shapes (str / list of dict / Content blocks).
    This function normalizes all shapes to str, for use by _execute_graph's streaming token push.
    """
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
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)


def _noop_emitter(*args, **kwargs) -> None:  # pragma: no cover
    return None


def _noop_stream(text: str) -> None:  # pragma: no cover
    logger.info(f"_noop_stream", text=text)
    return None


def _annotate_langfuse_tool_span(
    *,
    tool_name: str,
    agent_namespace: str,
    task_type: str,
) -> None:
    """Attach metadata labels to the current Langfuse observation.

    Triggered by _wrapped each time a make_tool-decorated tool is called. The LangChain
    CallbackHandler has already opened an observation around the tool call; this function
    only appends metadata and does not create another span.
    Langfuse disabled / package not installed / call failed -> silent noop.
    """
    try:
        from agent_kit.harness import HARNESS_OBS

        if not getattr(HARNESS_OBS, "_langfuse_enabled", False):
            return
        client = getattr(HARNESS_OBS, "_langfuse_client", None)
        if client is None:
            return
        client.update_current_observation(
            metadata={
                "agent_namespace": agent_namespace,
                "task_type": task_type,
                "tool_name": tool_name,
            }
        )
    except Exception:
        # Silent: observability must not drag down the tool call
        pass


# ---------------------------------------------------------------------------
# AgentRuntime: base class shared across forms
# ---------------------------------------------------------------------------

class AgentRuntime(ABC, Generic[ResultT]):
    """Common runtime base class shared across Agent forms.

    Subclasses (DeepAgentRuntime / ReactAgentRuntime / StateGraphRuntime / ...)
    only need to implement ``_build_graph()`` + ``_execute_graph(...)`` to gain a complete:
    - 12 hooks (5 required + 3 lifecycle + 4 optional)
    - make_tool closure-based tool factory
    - run() state machine entry point
    - error classification + metric/stream callback injection

    Form-specific hooks (subagents / memory / interrupt_on / response_format) are
    implemented solely by DeepAgentRuntime, keeping the base class clean.

    Run() execution flow (key decision points)::

         run(state, query)
            │
            ▼
        ┌───────────────┐
        │  before_call  │── returns Command ────────► return directly (**skips result construction,
        │   (state)     │                          agent call, finalize, metric**)
        └───────┬───────┘
                │ None
                ▼
        construct result + enter try
                │
                ▼
        ┌────────────────────┐
        │ should_run_agent   │── False ──► skip _execute_graph, **still run finalize**
        │  (state, query)    │
        └────────┬───────────┘
                 │ True
                 ▼
        build_system_prompt → augment_skills → build_user_content → _execute_graph
                 │ (exception path)
                 ▼
              on_failure → result.failed = True (on transport failure, **raise directly**)
                 │
                 ▼
              after_agent (called in finally, whether success or failure)
                 │
                 ▼
              finalize(state, result, query) → return Command

    Decision tree ("which hook should I use to skip the agent?")::

        Want to skip both the agent AND finalize (return a fixed Command directly)?
            → before_call returns Command
            Typical: state precheck failure, node needs to short-circuit to the next node

        Only skip the agent call, but still run finalize to output a result?
            → should_run_agent returns False
            Typical: low-signal ack ("嗯""好") saves LLM cost, but still runs finalize to stream a reply

        Want to decide after result is constructed? Not possible -- before_call is called before result,
        should_run_agent is called after result. Follow this order when deciding.
    """

    # ───── Config options subclasses may override ──────────────────────────
    metric_namespace: str = "agent"
    thread_id_prefix: str = "agent"
    fallback_reply: str = "请继续提供您的需求信息，帮助我们为您精准匹配。"
    cache_graph: bool = True
    """Whether to cache the product of _build_graph().

    - True (default): cache the graph after the first run; subsequent runs reuse it directly.
      ``build_tools()`` / ``collect_skill_tools()`` are only called on the first round.
    - False: rebuild the graph on every run. Suitable for scenarios like bargaining nodes that need
      to decide graph topology based on state, or that need to re-collect dynamic tools each round.
      The cost is an extra _build_graph call each round.
    """

    def __init__(self, *, llm: Optional[Any] = None) -> None:
        self._llm: Any = llm
        self._graph: Any = None
        self._current_result_var: contextvars.ContextVar = contextvars.ContextVar(
            f"_{self.metric_namespace}_result_{id(self)}"
        )
        # request_scope: a turn-internal scratch area for each run(), isolated by ContextVar,
        # so multiple instances / concurrent runs of the same instance never cross-contaminate.
        # Business code reads/writes it in before_call/after_agent.
        self._request_scope_var: contextvars.ContextVar = contextvars.ContextVar(
            f"_{self.metric_namespace}_request_scope_{id(self)}"
        )
        # stream_callback also uses a ContextVar: it was originally a plain instance attribute,
        # and concurrent runs of the same instance would cross-contaminate
        # (thread A's callback overwritten by thread B). set at run() entry / reset at exit.
        self._stream_callback_var: contextvars.ContextVar = contextvars.ContextVar(
            f"_{self.metric_namespace}_stream_cb_{id(self)}"
        )

    # P2 (ADR-002): detect whether subclasses override deprecated hooks and emit a DeprecationWarning.
    # __init_subclass__ only checks in the *directly defined* subclass (cls.__dict__), not triggered through the inheritance chain.
    # The three Runtime-form subclasses (DeepAgentRuntime / CreateAgentRuntime / StateGraphRuntime)
    # do not override these hooks themselves, so they won't trigger; only business subclasses that override will.
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for hook_name, replacement in _DEPRECATED_HOOK_REPLACEMENTS.items():
            own_method = cls.__dict__.get(hook_name)
            if own_method is None:
                continue
            base_method = getattr(AgentRuntime, hook_name, None)
            if own_method is base_method:
                continue
            warnings.warn(
                f"{cls.__module__}.{cls.__qualname__}: overriding {hook_name!r} "
                f"is deprecated and will be removed in the next minor release; "
                f"use {replacement} via middleware_extra() instead. See ADR-002.",
                DeprecationWarning,
                stacklevel=2,
            )

    # ───── 5 required hooks to implement ──────────────────────────

    @property
    @abstractmethod
    def result_class(self) -> type[ResultT]: ...
    @abstractmethod
    def build_system_prompt(self, state: Any, user_query: str) -> str: ...
    @abstractmethod
    def build_user_content(self, state: Any, user_query: str) -> str: ...
    @abstractmethod
    def build_tools(self) -> list: ...
    @abstractmethod
    def finalize(self, state: Any, result: ResultT, user_query: str) -> Command: ...

    # ───── 3 lifecycle hooks ───────────────────────────

    def before_call(self, state: Any) -> Optional[Command]:
        """Called first at run() entry, before result construction.

        .. deprecated::
            As of P2 (ADR-002), overriding this hook emits a ``DeprecationWarning``, and it will be removed
            in the next minor version. Use ``EntryGuardMiddleware`` injected via ``middleware_extra()`` instead.
            This hook is only required when you still need ``Command(goto="some_node")`` to jump to a custom node
            (middleware only supports ``jump_to=["end"]``).

        Returning a ``Command`` **fully short-circuits** -- skips result, agent, finalize, metric,
        and returns that Command directly.

        Returning ``None`` continues the subsequent flow (result → should_run_agent → execute → finalize).

        Typical uses:
        - State precheck failure needs to return a fixed reply directly
        - Node needs to short-circuit to the next node (``Command(goto=...)``)
        - Category stage not yet confirmed, no need to construct result + run agent

        Compared with ``should_run_agent``:
        - before_call skips finalize; should_run_agent still runs finalize
        - before_call is before result; should_run_agent is after result
        """
        return None

    def should_run_agent(self, state: Any, user_query: str) -> bool:
        """Decide whether to actually call the graph this round. Default True.

        .. deprecated::
            As of P2 (ADR-002), overriding this hook emits a ``DeprecationWarning``, and it will be removed
            in the next minor version. Use ``ModelSkipMiddleware`` injected via ``middleware_extra()`` instead.

        When it returns False, **only _execute_graph is skipped**; ``after_agent`` + ``finalize`` still run.
        ``result`` is already constructed but ``result.reply`` is empty / ``raw_messages`` is empty.

        Typical uses:
        - Low-signal ack ("嗯""好""ok") saves LLM cost, but still runs finalize to stream a reply
        - Cache hit, no need to re-run the agent
        - All needed info already collected via ``request_scope``, skip the agent and output the result directly

        Compared with ``before_call``:
        - should_run_agent still runs finalize; before_call returning a Command fully short-circuits
        - should_run_agent can read the constructed result; at before_call time result does not yet exist
        """
        return True

    def after_agent(self, state: Any, result: ResultT, user_query: str) -> None:
        """Hook after the Agent runs, before finalize. result is readable/writable."""
        return None

    # ───── 4 optional hooks ───────────────────────────────

    def context_extra_fields_schema(self) -> dict:
        """Declare fields for the dynamic_prompt context beyond system_prompt."""
        return {}

    def context_extra_fields(self, state: Any) -> dict:
        """Provide values for the extra context fields at invoke time this round."""
        return {}

    def middleware_extra(self) -> list:
        """Extra business LangChain middleware."""
        logger.info(f"base_middleware_extra")
        return []

    def on_failure(self, state: Any, user_query: str, error: Exception) -> str:
        """Fallback reply when the Agent errors. Returns a fixed message by default.

        .. deprecated::
            As of P2 (ADR-002), overriding this hook emits a ``DeprecationWarning``, and it will be removed
            in the next minor version. Use ``FallbackReplyMiddleware`` injected via ``middleware_extra()``;
            for custom branching by exception type use the ``on_error=lambda e: ...`` parameter.
        """
        return self.fallback_reply

    # ───── Skills hooks (added in PR2) ─────────────────────
    # By default skills_dir() returns None → skill system fully disabled, behavior identical to pre-PR1

    def skills_dir(self) -> Optional[str]:
        """Return this Agent's skills root directory. Returning None (default) = skill system disabled.

        To enable: override in a subclass to return a path, e.g. ``return "./skills"``.
        """
        return None

    def skill_match_top_k(self) -> int:
        """top_k for skill matching; default 3."""
        return 3

    def skill_match_threshold(self) -> float:
        """Confidence threshold for skill matching; default 0.3."""
        return 0.3

    def build_skill_orchestrator(self):
        """Hook: construct the SkillOrchestrator; by default auto-created and cached based on skills_dir().

        Business code can override to inject a custom matcher / adapter. Returning None is equivalent to disabled.
        """
        skills_dir = self.skills_dir()
        if not skills_dir:
            return None
        # Lazy-load cache
        cached = getattr(self, "_skill_orchestrator", None)
        if cached is not None:
            return cached
        from agent_kit.skills import SkillOrchestrator

        orch = SkillOrchestrator.create_default(skills_dir)
        self._skill_orchestrator = orch
        return orch

    def collect_skill_tools(self) -> list:
        """PR3: enumerate all ``executable`` / ``hybrid`` skills under skills_dir,
        and materialize them all into LangChain Tools.

        Collected once during the ``_build_graph()`` stage (the graph cache is built only once).
        Matching (Matcher) only affects system prompt augmentation at each query,
        telling the LLM "which tool to use now". This is the standard Anthropic Agent Skills pattern.

        Failed skills are silently skipped + warn logged, without affecting the main flow.
        """
        orch = self.build_skill_orchestrator()
        if orch is None:
            return []
        try:
            # Full manifest (already discovered) → load body → compile executable tool
            all_manifests = orch.registry.all(enabled_only=True)
            executable = [
                m for m in all_manifests if m.mode in ("executable", "hybrid")
            ]
            if not executable:
                return []
            # Load body (in_process adapter doesn't need body, but kept consistent)
            for m in executable:
                if m.body is None:
                    orch.loader.load_body(m.skill_id)
            return orch.materialize_tools(executable)
        except Exception as e:
            logger.warning(
                f"{type(self).__name__}: collect_skill_tools failed "
                f"(continuing without skill tools): {e}"
            )
            return []

    # ───── make_tool: tool factory that closure-binds result ────────

    def make_tool(self, fn):
        """Convert fn(result, *args, **kwargs) -> str into a LangChain @tool.

        result is automatically injected by this instance's ContextVar.
        The closure binds this instance's ContextVar, supporting multi-instance isolation within the same process.

        Langfuse observability: the tool call automatically appears as a TOOL observation in the trace
        (created by the LangChain CallbackHandler); agent_namespace / task_type
        are automatically applied to all child observations via HARNESS_OBS.span()'s propagate_attributes,
        with no need to manually instrument each tool call.
        """
        from langchain_core.tools import tool

        if not fn.__doc__:
            raise ValueError(
                f"make_tool: function {fn.__name__!r} missing docstring; "
                "Agent 工具必须有 docstring 作为 LLM 工具说明"
            )

        node_result_var = self._current_result_var
        agent_namespace = self.metric_namespace
        task_type = getattr(self, "task_type", "") or ""
        tool_name = fn.__name__

        @functools.wraps(fn)
        def _wrapped(*args, **kwargs):
            result = node_result_var.get()
            _annotate_langfuse_tool_span(
                tool_name=tool_name,
                agent_namespace=agent_namespace,
                task_type=task_type,
            )
            return fn(result, *args, **kwargs)

        try:
            import inspect
            orig_sig = inspect.signature(fn)
            params = list(orig_sig.parameters.values())
            if params and params[0].name == "result":
                new_sig = orig_sig.replace(parameters=params[1:])
                _wrapped.__signature__ = new_sig  # type: ignore[attr-defined]
                ann = dict(getattr(fn, "__annotations__", {}))
                ann.pop("result", None)
                _wrapped.__annotations__ = ann
        except (ValueError, TypeError):
            pass

        return tool(_wrapped)

    @property
    def current_result(self) -> ResultT:
        return self._current_result_var.get()

    @property
    def request_scope(self) -> dict:
        """The scratch area for this run(). Isolated by ContextVar → multiple instances / concurrent runs of the same instance never cross-contaminate.

        Typical usage: business code writes ``self.request_scope["phase"] = ...`` in ``before_call``,
        and reads it in ``after_agent`` / ``finalize``.
        run() automatically set({}) at entry, reset at exit.
        """
        try:
            return self._request_scope_var.get()
        except LookupError:
            # Caller accessed it outside run(); return an empty dict to avoid AttributeError
            return {}

    @property
    def _stream_callback(self) -> StreamCallback:
        """The stream callback for the current run() context. ContextVar-isolated, concurrency-safe."""
        try:
            return self._stream_callback_var.get()
        except LookupError:
            return _noop_stream

    @_stream_callback.setter
    def _stream_callback(self, cb: StreamCallback) -> None:
        """Preserve the old interface's write semantics; internally sets to the ContextVar. Note: only valid within the run() context."""
        self._stream_callback_var.set(cb)

    def on_stream_token(self, token: str) -> Optional[str]:
        """Streaming token hook. ``_execute_graph`` calls this hook once before calling ``_stream_callback``.

        - Return ``None`` or the original token: keep default behavior (push to stream_callback)
        - Return ``""``: swallow this token (do not push downstream)
        - Return a new string: replace the token

        Typical usage: when a business subclass needs to buffer all agent tokens for later concatenation,
        append here to ``self.request_scope["tokens"]``.
        """
        return token

    def _dispatch_stream_token(self, token: str) -> None:
        """Runtime-internal use: on_stream_token hook + stream_callback push.

        Subclasses should not override this method; to intercept tokens, override ``on_stream_token``.
        """
        try:
            transformed = self.on_stream_token(token)
        except Exception as e:
            logger.warning(
                f"{type(self).__name__}: on_stream_token raised: {e}"
            )
            transformed = token
        if transformed is None:
            transformed = token
        if transformed:
            self._stream_callback(transformed)


    def get_tools_for_testing(self) -> "tuple[list, ResultT]":
        """For unit tests only: construct a result, bind it to the ContextVar, and return (tools, result)."""
        result = self.result_class()
        self._current_result_var.set(result)
        return self.build_tools(), result

    # ───── Shared boilerplate for DeepAgent / CreateAgent forms ──────────
    # context_schema / dynamic_prompt / tool assembly / streaming loop / extract reply
    # StateGraphRuntime does not follow this path (it assembles its own state machine).

    def _build_context_schema(self):
        """Dynamically generate a Pydantic schema based on the subclass's context_extra_fields_schema()."""
        from pydantic import create_model

        extra = self.context_extra_fields_schema() or {}
        return create_model(
            f"{type(self).__name__}Context",
            system_prompt=(str, ""),
            sys_conversation_id=(str,""),
            **extra,
        )

    def _build_context(self, fields: dict):
        return self._build_context_schema()(**fields)

    def _dynamic_system_prompt_middleware(self, default_fallback: str = "你是一个智能助手。"):
        """Return a dynamic_prompt middleware that takes the prompt from ctx.system_prompt (falls back if empty)."""
        from langchain.agents.middleware.types import dynamic_prompt, ModelRequest

        @dynamic_prompt
        def _dyn(request: ModelRequest) -> str:
            ctx = request.runtime.context
            if ctx and hasattr(ctx, "system_prompt") and ctx.system_prompt:
                return ctx.system_prompt
            return default_fallback

        return _dyn

    def _collect_all_tools(self) -> list:
        """Merge build_tools + collect_skill_tools, with unified logging."""
        tools = list(self.build_tools() or [])
        skill_tools = self.collect_skill_tools() or []
        if skill_tools:
            tools.extend(skill_tools)
            logger.info(
                f"{type(self).__name__}: collected {len(skill_tools)} skill tools"
            )
        return tools

    def _stream_agent_messages(
        self,
        *,
        graph: Any,
        input_msg: dict,
        ctx: Any,
        thread_id: str,
    ) -> tuple[dict, bool]:
        """Run graph.stream(stream_mode='messages'), pushing each token to _dispatch_stream_token.

        Returns (out_state, streamed_any). Reused by DeepAgent / CreateAgent.
        """
        from agent_kit.harness import HARNESS_OBS
        from langchain_core.messages import AIMessageChunk

        streamed_any = False
        stream_kwargs: dict[str, Any] = {"stream_mode": "messages"}
        if ctx is not None:
            stream_kwargs["context"] = ctx
        with HARNESS_OBS.span(
            f"{self.metric_namespace}_agent",
            session_id=thread_id,
            metadata={
                "agent_namespace": self.metric_namespace,
                "task_type": getattr(self, "task_type", "") or "",
            },
        ) as span:
            config = {
                "configurable": {"thread_id": thread_id},
                "callbacks": span.callbacks,
            }
            for chunk, _meta in graph.stream(
                input_msg, config=config, **stream_kwargs
            ):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                if getattr(chunk, "tool_call_chunks", None):
                    continue
                token = extract_chunk_text(chunk.content)
                if not token:
                    continue
                streamed_any = True
                self._dispatch_stream_token(token)

            out = graph.get_state(config).values
        return out, streamed_any

    @staticmethod
    def _extract_last_reply(all_messages: list) -> str:
        """Find the last non-tool_call text from the end of the message stream to use as the reply."""
        for m in reversed(all_messages):
            if hasattr(m, "content") and not hasattr(m, "tool_call_id"):
                content = extract_chunk_text(getattr(m, "content", ""))
                if content and not getattr(m, "tool_calls", None):
                    return content.strip()
        return ""

    # ───── Low-level hooks each Runtime must implement ──────────────

    @abstractmethod
    def _build_graph(
        self,
        *,
        state: Any = None,
        system_prompt: str = "",
        user_content: str = "",
    ):
        """Construct the concrete LangGraph instance for this form.

        DeepAgentRuntime  → create_deep_agent(...)
        ReactAgentRuntime → create_react_agent(...)
        StateGraphRuntime → self.build_state_graph(...).compile(...)

        The kwargs ``state/system_prompt/user_content`` are only passed through by
        ``_get_graph(...)`` when ``cache_graph=False``; in cache mode they are placeholder empty values.
        """

    @abstractmethod
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
        """Run the graph once, writing results back to result (reply / raw_messages / extra)."""

    # ───── LLM factory (raises by default; must be injected or overridden by subclass/Harness) ────

    def _get_llm(self):
        if self._llm is None:
            raise NotImplementedError(
                "AgentRuntime._get_llm: 未注入 LLM；请通过构造参数 llm=... 注入，"
                "或在子类/适配层重写 _get_llm() 接入具体 LLM 工厂"
            )
        return self._llm

    def _get_graph(
        self,
        *,
        state: Any = None,
        system_prompt: str = "",
        user_content: str = "",
    ):
        """Decide whether to reuse the graph based on cache_graph.

        - cache_graph=True (default): lazy-load and cache; state/system_prompt/user_content are ignored.
        - cache_graph=False: rebuild each round and pass state/system_prompt/user_content through to
          ``_build_graph(...)``, to decide graph topology per turn.
        """
        if not self.cache_graph:
            graph = self._build_graph(
                state=state,
                system_prompt=system_prompt,
                user_content=user_content,
            )
            logger.debug(
                f"{type(self).__name__}: graph rebuilt (cache_graph=False, ns={self.metric_namespace})"
            )
            return graph
        if self._graph is None:
            self._graph = self._build_graph()
            logger.info(f"{type(self).__name__}: graph built (ns={self.metric_namespace})")
        return self._graph

    def invalidate_graph(self) -> None:
        """Manually clear the cached graph, rebuilding it on the next _get_graph() call.

        Typical scenario: after a business node dynamically registers a new skill / switches the LLM,
        the graph needs to be reassembled.
        When cache_graph=False this method has no effect on behavior.
        """
        self._graph = None

    def _make_thread_id(self, state: Any) -> str:
        rt = None
        if hasattr(state, "get"):
            rt = state.get("rt_thread_id") or state.get("sys_conversation_id")
        return f"{self.thread_id_prefix}__{rt or 'default'}"

    # ───── run(): state machine entry point ──────────────────────────

    def run(
        self,
        state: Any,
        user_query: str,
        *,
        stream_callback: Optional[StreamCallback] = None,
        counter_emitter: Optional[MetricEmitter] = None,
        histogram_emitter: Optional[MetricEmitter] = None,
    ) -> Command:
        """Agent state machine execution entry point, returns a LangGraph Command.

        Execution order:
            before_call → construct result → should_run_agent → _execute_graph
            → after_agent → finalize
        """
        stream_token = self._stream_callback_var.set(stream_callback or _noop_stream)
        emit_counter = counter_emitter or _noop_emitter
        emit_histogram = histogram_emitter or _noop_emitter

        # request_scope scratch area isolated per run(); set before before_call so before_call can write to it
        scope_token = self._request_scope_var.set({})

        try:
            t0 = time.perf_counter()
            try:
                cmd = self.before_call(state)
            except Exception as e:
                err_kind = classify_error(str(e))
                logger.error(
                    f"{type(self).__name__}: before_call raised kind={err_kind} err={e}",
                    exc_info=True,
                )
                emit_counter(
                    f"{self.metric_namespace}.agent_failed",
                    error_class=type(e).__name__,
                    error_kind=err_kind,
                    stage="before_call",
                )
                emit_histogram(
                    f"{self.metric_namespace}.agent_run_latency_ms",
                    value=(time.perf_counter() - t0) * 1000,
                    outcome="error",
                )
                raise
            if cmd is not None:
                emit_histogram(
                    f"{self.metric_namespace}.agent_run_latency_ms",
                    value=(time.perf_counter() - t0) * 1000,
                    outcome="before_call_short_circuit",
                )
                return cmd

            result: ResultT = self.result_class()
            ctx_token = self._current_result_var.set(result)

            agent_ran = False
            try:
                if self.should_run_agent(state, user_query):
                    agent_ran = True
                    system_prompt = self.build_system_prompt(state, user_query)

                    try:
                        orch = self.build_skill_orchestrator()
                        if orch is not None:
                            system_prompt = orch.match_and_augment(
                                query=user_query,
                                base_prompt=system_prompt,
                                top_k=self.skill_match_top_k(),
                                threshold=self.skill_match_threshold(),
                            )
                    except Exception as skill_err:
                        logger.warning(
                            f"{type(self).__name__}: skill augmentation failed "
                            f"(continuing without skills): {skill_err}"
                        )

                    user_content = self.build_user_content(state, user_query)
                    thread_id = self._make_thread_id(state)
                    graph = self._get_graph(state=state, system_prompt=system_prompt, user_content=user_content)
                    self._execute_graph(
                        graph=graph,
                        state=state,
                        system_prompt=system_prompt,
                        user_content=user_content,
                        thread_id=thread_id,
                        result=result,
                    )
            except Exception as e:
                err_text = str(e)
                err_kind = classify_error(err_text)
                logger.error(
                    f"{type(self).__name__}: agent run failed kind={err_kind} err={err_text}",
                    exc_info=True,
                )
                emit_counter(
                    f"{self.metric_namespace}.agent_failed",
                    error_class=type(e).__name__,
                    error_kind=err_kind,
                )
                result.failed = True
                reraise_if_critical(e)
                try:
                    result.reply = self.on_failure(state, user_query, e)
                except Exception as fb_err:
                    logger.error(
                        f"{type(self).__name__}: on_failure also failed: {fb_err}", exc_info=True
                    )
                    result.reply = self.fallback_reply
            finally:
                # outcome three states:
                #  - error: result.failed=True (including the case where should_run_agent itself raises)
                #  - ok: agent ran normally to completion
                #  - should_run_agent_skipped: business actively decided not to run the agent (short-circuit, low-signal ack, etc.)
                if result.failed:
                    outcome = "error"
                elif agent_ran:
                    outcome = "ok"
                else:
                    outcome = "should_run_agent_skipped"
                emit_histogram(
                    f"{self.metric_namespace}.agent_run_latency_ms",
                    value=(time.perf_counter() - t0) * 1000,
                    outcome=outcome,
                )
                try:
                    self.after_agent(state, result, user_query)
                except Exception as ae:
                    logger.error(
                        f"{type(self).__name__}: after_agent hook failed: {ae}", exc_info=True
                    )
                    reraise_if_critical(ae)
                self._current_result_var.reset(ctx_token)

            return self.finalize(state, result, user_query)
        finally:
            self._request_scope_var.reset(scope_token)
            self._stream_callback_var.reset(stream_token)
