"""
AgentRuntime：跨 Agent 形态共享的统一运行时基类。

设计意图：
- 所有 Agent 形态（DeepAgent / ReAct / 自建 StateGraph 等）继承这个基类
- 共享：钩子骨架、make_tool、run() 状态机、错误归类、metric/stream callback 注入
- 各 Runtime 子类只需实现两个底层钩子：
  - ``_build_graph()``：构造具体形态的 LangGraph 实例
  - ``_execute_graph(...)``：跑一次 graph + 收 result

向上对接 Harness（Day3-7）：HarnessBacked mixin 通过重写 _get_llm / build_system_prompt /
build_tools 把任意 AgentRuntime 接到 Model Router / Prompt Registry / Skill Adapter。

不依赖：
- 任何 workflow 引擎类型（BaseNode 等）
- 任何具体仓库的 metric / LLM 工厂
- Langfuse（可选，由 Runtime 子类按需 import）
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


# P2（ADR-002）：以下钩子已被对应 LangChain Middleware 覆盖；override 时发 DeprecationWarning。
# 将在 P3（下一个 minor）从基类删除。
_DEPRECATED_HOOK_REPLACEMENTS: dict[str, str] = {
    "before_call": "EntryGuardMiddleware",
    "should_run_agent": "ModelSkipMiddleware",
    "on_failure": "FallbackReplyMiddleware",
}


# ---------------------------------------------------------------------------
# Result 基类
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    """所有 Agent 运行结果的统一基类。

    业务子类继承并加业务字段。Runtime-specific 附加信息（如 DeepAgent 的 todos）
    塞 ``extra`` dict，避免子类 isinstance 区分 Runtime 类型。
    """

    reply: str = ""
    """Agent 最终生成给用户的文本回复。"""

    failed: bool = False
    """Agent 整体异常标记。"""

    raw_messages: list = Field(default_factory=list)
    """Agent 运行后 graph state 里的完整 messages 列表。"""

    extra: dict = Field(default_factory=dict)
    """Runtime-specific 数据（如 ``extra['todos']`` for DeepAgent）。"""


ResultT = TypeVar("ResultT", bound=AgentResult)


# ---------------------------------------------------------------------------
# 错误归类
# ---------------------------------------------------------------------------

def classify_error(error_text: str) -> str:
    """把 LLM/Agent 异常归到 metric label：compliance / tool_json / network / other。"""
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


# Callback 类型别名
StreamCallback = Callable[[str], None]
MetricEmitter = Callable[..., None]


def extract_chunk_text(content: Any) -> str:
    """Normalize AIMessageChunk.content to a plain string for streaming.

    LangChain 不同 provider 返回的 content 形态各异（str / list of dict / Content blocks）。
    本函数把所有形态归一为 str，供 _execute_graph 流式 token 推送使用。
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
    """在当前 Langfuse observation 上打 metadata 标签。

    每次 make_tool 装饰的工具被调用时由 _wrapped 触发。LangChain CallbackHandler
    已经在 tool 调用外层开了 observation，本函数只追加 metadata 不另建 span。
    Langfuse 未启用 / 包未安装 / 调用失败 → 静默 noop。
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
        # 静默：观测点不能拖垮 tool 调用
        pass


# ---------------------------------------------------------------------------
# AgentRuntime：跨形态共享基类
# ---------------------------------------------------------------------------

class AgentRuntime(ABC, Generic[ResultT]):
    """跨 Agent 形态共享的通用运行时基类。

    子类（DeepAgentRuntime / ReactAgentRuntime / StateGraphRuntime / ...）
    实现 ``_build_graph()`` + ``_execute_graph(...)`` 即可拥有完整的：
    - 12 个钩子（5 必须 + 3 生命周期 + 4 可选）
    - make_tool 闭包工具工厂
    - run() 状态机入口
    - 错误归类 + metric/stream callback 注入

    跨形态独有钩子（subagents / memory / interrupt_on / response_format）由
    DeepAgentRuntime 单独实现，不污染基类。

    Run() 执行流（关键决策点）::

         run(state, query)
            │
            ▼
        ┌───────────────┐
        │  before_call  │── 返回 Command ────────► 直接 return（**跳过 result 构造、
        │   (state)     │                          agent 调用、finalize、metric**）
        └───────┬───────┘
                │ None
                ▼
        构造 result + 进入 try
                │
                ▼
        ┌────────────────────┐
        │ should_run_agent   │── False ──► 跳过 _execute_graph，**仍走 finalize**
        │  (state, query)    │
        └────────┬───────────┘
                 │ True
                 ▼
        build_system_prompt → augment_skills → build_user_content → _execute_graph
                 │ (异常路径)
                 ▼
              on_failure → result.failed = True（transport 失败则 **直接 raise**）
                 │
                 ▼
              after_agent (finally 内调，无论成功失败)
                 │
                 ▼
              finalize(state, result, query) → return Command

    决策树（"我该用哪个钩子跳过 agent？"）::

        既要跳过 agent，又要跳过 finalize（直接返回固定 Command）？
            → before_call 返回 Command
            典型：状态预检失败、节点要短路到下一节点

        只跳过 agent 调用，但仍要走 finalize 输出结果？
            → should_run_agent 返回 False
            典型：低信号 ack（"嗯""好"）省 LLM 成本，但仍要走 finalize 推流回复

        要在 result 构造完之后再决定？不可能 —— before_call 在 result 之前调，
        should_run_agent 在 result 之后调。请按这个顺序判断。
    """

    # ───── 子类可覆盖的配置项 ──────────────────────────
    metric_namespace: str = "agent"
    thread_id_prefix: str = "agent"
    fallback_reply: str = "请继续提供您的需求信息，帮助我们为您精准匹配。"
    cache_graph: bool = True
    """是否缓存 _build_graph() 的产物。

    - True (默认)：第一次 run 后缓存 graph；后续 run 直接复用。
      ``build_tools()`` / ``collect_skill_tools()`` 只在第一轮被调用。
    - False：每次 run 都重建 graph。适合议价节点等需要按 state 决定 graph 拓扑、
      或需要每轮重新 collect 动态 tools 的场景。代价是每轮多一次 _build_graph 开销。
    """

    def __init__(self, *, llm: Optional[Any] = None) -> None:
        self._llm: Any = llm
        self._graph: Any = None
        self._current_result_var: contextvars.ContextVar = contextvars.ContextVar(
            f"_{self.metric_namespace}_result_{id(self)}"
        )
        # request_scope：每次 run() 的 turn-internal 暂存区，由 ContextVar 隔离，
        # 多实例 / 并发跑同实例都不会串。业务在 before_call/after_agent 里读写。
        self._request_scope_var: contextvars.ContextVar = contextvars.ContextVar(
            f"_{self.metric_namespace}_request_scope_{id(self)}"
        )
        # stream_callback 也走 ContextVar：原本是普通实例属性，并发跑同实例会串
        # （线程 A 的 callback 被线程 B 覆盖）。run() 入口 set / 出口 reset。
        self._stream_callback_var: contextvars.ContextVar = contextvars.ContextVar(
            f"_{self.metric_namespace}_stream_cb_{id(self)}"
        )

    # P2（ADR-002）：检测子类是否 override 已废弃的钩子，发 DeprecationWarning。
    # __init_subclass__ 只在 *直接定义* 的子类里检查（cls.__dict__），不会因继承链触发。
    # 三个 Runtime 形态子类（DeepAgentRuntime / CreateAgentRuntime / StateGraphRuntime）
    # 本身不 override 这些钩子，所以不会触发；业务子类 override 时才会触发。
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

    # ───── 5 个必须实现的钩子 ──────────────────────────

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

    # ───── 3 个生命周期钩子 ───────────────────────────

    def before_call(self, state: Any) -> Optional[Command]:
        """run() 入口最先调，在 result 构造之前。

        .. deprecated::
            P2（ADR-002）起 override 本钩子会发 ``DeprecationWarning``，下一个 minor
            版本移除。改用 ``EntryGuardMiddleware`` 通过 ``middleware_extra()`` 注入。
            仍需要 ``Command(goto="some_node")`` 跳转自定义节点的场景才必须用本钩子
            （middleware 仅支持 ``jump_to=["end"]``）。

        返回 ``Command`` 则 **完全短路** —— 跳过 result、agent、finalize、metric，
        直接返回该 Command。

        返回 ``None`` 则继续后续流程（result → should_run_agent → execute → finalize）。

        典型用途：
        - 状态预检失败需要直接返回固定回复
        - 节点要短路跳到下一节点（``Command(goto=...)``）
        - 类目阶段尚未确认，没必要构造 result + 跑 agent

        对比 ``should_run_agent``：
        - before_call 跳过 finalize；should_run_agent 仍走 finalize
        - before_call 在 result 之前；should_run_agent 在 result 之后
        """
        return None

    def should_run_agent(self, state: Any, user_query: str) -> bool:
        """决定本轮是否真正调用 graph。默认 True。

        .. deprecated::
            P2（ADR-002）起 override 本钩子会发 ``DeprecationWarning``，下一个 minor
            版本移除。改用 ``ModelSkipMiddleware`` 通过 ``middleware_extra()`` 注入。

        返回 False 时 **只跳过 _execute_graph**，仍然会走 ``after_agent`` + ``finalize``。
        ``result`` 已构造但 ``result.reply`` 为空 / ``raw_messages`` 为空。

        典型用途：
        - 低信号 ack（"嗯""好""ok"）省 LLM 成本，但仍要走 finalize 推流回复
        - 缓存命中无需重新跑 agent
        - 通过 ``request_scope`` 已经收集到全部所需信息，跳过 agent 直接出结果

        对比 ``before_call``：
        - should_run_agent 仍走 finalize；before_call 返回 Command 完全短路
        - should_run_agent 可读已构造的 result；before_call 时 result 还不存在
        """
        return True

    def after_agent(self, state: Any, result: ResultT, user_query: str) -> None:
        """Agent 跑完后、finalize 前的钩子。result 可读写。"""
        return None

    # ───── 4 个可选钩子 ───────────────────────────────

    def context_extra_fields_schema(self) -> dict:
        """声明 dynamic_prompt context 除 system_prompt 之外的字段。"""
        return {}

    def context_extra_fields(self, state: Any) -> dict:
        """本轮 invoke 时为额外 context 字段提供值。"""
        return {}

    def middleware_extra(self) -> list:
        """业务额外 LangChain middleware。"""
        logger.info(f"base_middleware_extra")
        return []

    def on_failure(self, state: Any, user_query: str, error: Exception) -> str:
        """Agent 异常时的兜底回复。默认返回固定话术。

        .. deprecated::
            P2（ADR-002）起 override 本钩子会发 ``DeprecationWarning``，下一个 minor
            版本移除。改用 ``FallbackReplyMiddleware`` 通过 ``middleware_extra()`` 注入；
            自定义按异常类型分支用 ``on_error=lambda e: ...`` 参数。
        """
        return self.fallback_reply

    # ───── Skills 钩子（PR2 加入）─────────────────────
    # 默认 skills_dir() 返回 None → 完全不启用 skill 系统，行为与 PR1 之前一致

    def skills_dir(self) -> Optional[str]:
        """返回本 Agent 的 skills 根目录。返回 None（默认）= 不启用 skill 系统。

        启用方式：在子类里 override 返回路径，例如 ``return "./skills"``。
        """
        return None

    def skill_match_top_k(self) -> int:
        """skill 匹配的 top_k；默认 3。"""
        return 3

    def skill_match_threshold(self) -> float:
        """skill 匹配的 confidence 阈值；默认 0.3。"""
        return 0.3

    def build_skill_orchestrator(self):
        """钩子：构造 SkillOrchestrator；默认基于 skills_dir() 自动创建并缓存。

        业务可重写以注入自定义 matcher / adapter。返回 None 等价于不启用。
        """
        skills_dir = self.skills_dir()
        if not skills_dir:
            return None
        # 懒加载缓存
        cached = getattr(self, "_skill_orchestrator", None)
        if cached is not None:
            return cached
        from agent_kit.skills import SkillOrchestrator

        orch = SkillOrchestrator.create_default(skills_dir)
        self._skill_orchestrator = orch
        return orch

    def collect_skill_tools(self) -> list:
        """PR3：枚举 skills_dir 下所有 ``executable`` / ``hybrid`` 的 skill，
        全部 materialize 成 LangChain Tools。

        在 ``_build_graph()`` 阶段一次性收集（graph 缓存只构建一次）。
        匹配（Matcher）只在每次 query 时影响 system prompt augmentation，
        告诉 LLM "现在该用哪个 tool"。这是 Anthropic Agent Skills 的标准模式。

        失败的 skill 静默 skip + warn log，不影响主流程。
        """
        orch = self.build_skill_orchestrator()
        if orch is None:
            return []
        try:
            # 全量 manifest（已 discover）→ 加载 body → 编译可执行 tool
            all_manifests = orch.registry.all(enabled_only=True)
            executable = [
                m for m in all_manifests if m.mode in ("executable", "hybrid")
            ]
            if not executable:
                return []
            # 加载 body（in_process adapter 不需要 body，但保持一致）
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

    # ───── make_tool：闭包绑定 result 的工具工厂 ────────

    def make_tool(self, fn):
        """把 fn(result, *args, **kwargs) -> str 转成 LangChain @tool。

        result 由本实例的 ContextVar 自动注入。
        闭包绑定本 instance 的 ContextVar，支持同进程多实例隔离。

        Langfuse 观测：tool 调用作为 TOOL observation 自动出现在 trace 里
        （由 LangChain CallbackHandler 创建）；agent_namespace / task_type
        通过 HARNESS_OBS.span() 的 propagate_attributes 自动套用到所有
        child observation，无需在每个 tool 调用里手动埋点。
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
        """本轮 run() 的暂存区。由 ContextVar 隔离 → 多实例 / 并发跑同实例都不串。

        典型用法：业务在 ``before_call`` 里写 ``self.request_scope["phase"] = ...``，
        在 ``after_agent`` / ``finalize`` 里读。
        run() 会在入口自动 set({})、出口 reset。
        """
        try:
            return self._request_scope_var.get()
        except LookupError:
            # 调用者在 run() 之外访问；返回空 dict 避免 AttributeError
            return {}

    @property
    def _stream_callback(self) -> StreamCallback:
        """当前 run() 上下文的 stream callback。ContextVar 隔离，并发安全。"""
        try:
            return self._stream_callback_var.get()
        except LookupError:
            return _noop_stream

    @_stream_callback.setter
    def _stream_callback(self, cb: StreamCallback) -> None:
        """保留老接口的写语义；内部 set 到 ContextVar。注意：仅在 run() 上下文内有效。"""
        self._stream_callback_var.set(cb)

    def on_stream_token(self, token: str) -> Optional[str]:
        """流式 token 钩子。``_execute_graph`` 在调 ``_stream_callback`` 前先调一遍本钩子。

        - 返回 ``None`` 或原 token：保持默认行为（推给 stream_callback）
        - 返回 ``""``：吞掉本 token（不推给下游）
        - 返回新字符串：替换 token

        典型用法：业务子类需要缓冲全部 agent token 做事后拼接时，
        在这里 append 到 ``self.request_scope["tokens"]``。
        """
        return token

    def _dispatch_stream_token(self, token: str) -> None:
        """Runtime 内部使用：on_stream_token 钩子 + stream_callback 推送。

        子类不应重写本方法；要拦截 token 请重写 ``on_stream_token``。
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
        """单测专用：构造一个 result 并绑到 ContextVar，返回 (tools, result)。"""
        result = self.result_class()
        self._current_result_var.set(result)
        return self.build_tools(), result

    # ───── DeepAgent / CreateAgent 形态共享样板 ──────────
    # context_schema / dynamic_prompt / tool 装配 / 流式循环 / 取 reply
    # StateGraphRuntime 不走这条路径（自己拼 state machine）。

    def _build_context_schema(self):
        """根据子类 context_extra_fields_schema() 动态生成 Pydantic schema。"""
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
        """返回一个 dynamic_prompt 中间件，从 ctx.system_prompt 取 prompt（空则回 fallback）。"""
        from langchain.agents.middleware.types import dynamic_prompt, ModelRequest

        @dynamic_prompt
        def _dyn(request: ModelRequest) -> str:
            ctx = request.runtime.context
            if ctx and hasattr(ctx, "system_prompt") and ctx.system_prompt:
                return ctx.system_prompt
            return default_fallback

        return _dyn

    def _collect_all_tools(self) -> list:
        """合并 build_tools + collect_skill_tools，附带统一日志。"""
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
        """跑 graph.stream(stream_mode='messages')，逐 token 推到 _dispatch_stream_token。

        返回 (out_state, streamed_any)。供 DeepAgent / CreateAgent 复用。
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
        """从消息流末尾找最后一条非 tool_call 的文本作为 reply。"""
        for m in reversed(all_messages):
            if hasattr(m, "content") and not hasattr(m, "tool_call_id"):
                content = extract_chunk_text(getattr(m, "content", ""))
                if content and not getattr(m, "tool_calls", None):
                    return content.strip()
        return ""

    # ───── 各 Runtime 必须实现的底层钩子 ──────────────

    @abstractmethod
    def _build_graph(
        self,
        *,
        state: Any = None,
        system_prompt: str = "",
        user_content: str = "",
    ):
        """构造具体形态的 LangGraph 实例。

        DeepAgentRuntime  → create_deep_agent(...)
        ReactAgentRuntime → create_react_agent(...)
        StateGraphRuntime → self.build_state_graph(...).compile(...)

        kwarg ``state/system_prompt/user_content`` 仅在 ``cache_graph=False`` 时由
        ``_get_graph(...)`` 透传过来；缓存模式下为占位空值。
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
        """跑一次 graph，把结果写回 result（reply / raw_messages / extra）。"""

    # ───── LLM 工厂（默认抛错，必须注入或由子类/Harness 重写）────

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
        """按 cache_graph 决定是否复用 graph。

        - cache_graph=True (默认): 懒加载并缓存；state/system_prompt/user_content 被忽略。
        - cache_graph=False: 每轮重建并把 state/system_prompt/user_content 透传给
          ``_build_graph(...)``，便于按 turn 决定 graph 拓扑。
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
        """手动清掉缓存的 graph，下次 _get_graph() 时重建。

        典型场景：业务节点动态注册新 skill / 切换 LLM 后，需要让 graph 重新装配。
        cache_graph=False 时本方法不影响行为。
        """
        self._graph = None

    def _make_thread_id(self, state: Any) -> str:
        rt = None
        if hasattr(state, "get"):
            rt = state.get("rt_thread_id") or state.get("sys_conversation_id")
        return f"{self.thread_id_prefix}__{rt or 'default'}"

    # ───── run()：状态机入口 ──────────────────────────

    def run(
        self,
        state: Any,
        user_query: str,
        *,
        stream_callback: Optional[StreamCallback] = None,
        counter_emitter: Optional[MetricEmitter] = None,
        histogram_emitter: Optional[MetricEmitter] = None,
    ) -> Command:
        """Agent 状态机执行入口，返回 LangGraph Command。

        执行顺序：
            before_call → 构造 result → should_run_agent → _execute_graph
            → after_agent → finalize
        """
        stream_token = self._stream_callback_var.set(stream_callback or _noop_stream)
        emit_counter = counter_emitter or _noop_emitter
        emit_histogram = histogram_emitter or _noop_emitter

        # 每轮 run() 隔离的 request_scope 暂存区；before_call 之前 set 以便 before_call 可写
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
                # outcome 三态：
                #  - error: result.failed=True（含 should_run_agent 自身抛异常的情况）
                #  - ok: agent 正常跑完
                #  - should_run_agent_skipped: 业务主动判定不跑 agent（短路、低信号 ack 等）
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
