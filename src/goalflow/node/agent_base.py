"""``node/agent_base``：workflow 节点新一代 base 类。

基于 ADR-003 的 ``agent_kit.Agent`` + ``GraphBuilder`` 策略，替代老的：

- ``node/deep_agent_base.py::DeepAgentBaseNode``
- ``node/create_agent_base.py::CreateAgentBaseNode``
- ``node/state_graph_base.py::StateGraphBaseNode``

老 3 个 base 仍可用（标记为 ``DeprecationWarning``），业务节点零改动；新节点推荐继承本类。

设计要点（ADR-004）：

- **单一基类，graph 形态参数化**：通过 ``build_graph_builder_for_agent()`` 切换
  ``ReactGraphBuilder``（默认） / ``DeepGraphBuilder`` / ``CustomGraphBuilder``
- **钩子从 12 → 4**：业务子类只实现 ``output_schema`` / ``build_prompt`` /
  ``serialize_output`` / [可选] ``format_user_input``；其它一切走 LangChain
  ``AgentMiddleware``
- **workflow 桥接**：``BaseNode.call(state) → Agent.run(state, sys_query)``；
  ``stream_callback`` 通过 ``RunnableConfig.configurable["stream_callback"]``
  注入（避免 ContextVar 隐式状态）
- **Harness 共享**：默认 ``default_harness()``，与老 API 共用 ``HARNESS_*`` 单例

最小用法::

    from goalflow.node.agent_base import AgentBaseNode
    from pydantic import BaseModel
    from langgraph.types import Command

    class MyOutput(BaseModel):
        reply: str = ""
        label: str = ""

    class CategoryClassifyNode(AgentBaseNode[MyOutput]):
        name = "category_classify"  # 同时是 harness.router.get 的 task_type

        def output_schema(self): return MyOutput
        def build_prompt(self, state): return "你是企业服务类目分类器。"
        def serialize_output(self, state, output):
            if isinstance(output, MyOutput):
                return Command(update={"reply": output.reply, "label": output.label})
            return Command(update={"reply": str(output)})

切换底层 graph 形态::

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
    """workflow 节点 + ``agent_kit.Agent`` 组合（ADR-004，替老 3 个 ``*BaseNode``）。

    业务子类必须实现：

    - ``output_schema() -> type[BaseModel]``（``Agent`` 抽象）
    - ``build_prompt(state) -> str``（``Agent`` 抽象）
    - ``build_command(state, output) -> Command``（**本类抽象**：把 Agent 产物翻译为
      LangGraph ``Command``，决定 workflow 路由 / state 更新）

    可选 override（默认实现合理）：

    - ``format_user_input(state, query) -> str``（``Agent`` 可选）：默认透传 query
    - ``format_output(state, output) -> Any``（``Agent`` 可选）：默认透传 graph 输出；
      想做 typed parsing / post-process 的子类 override

    通过 ``build_graph_builder_for_agent()`` 切换底层 graph 形态：

    - 默认 ``ReactGraphBuilder``（替老 ``CreateAgentBaseNode``）
    - ``DeepGraphBuilder``（替老 ``DeepAgentBaseNode``）
    - ``CustomGraphBuilder``（替老 ``StateGraphBaseNode``）

    可选 override 的 5 个工厂钩子（按类层级）：

    - ``build_tools_for_agent() -> list``
    - ``build_middleware_for_agent() -> list``
    - ``build_graph_builder_for_agent() -> Optional[GraphBuilder]``
    - ``build_harness_for_agent() -> Optional[Harness]``
    - ``cache_graph: bool``（类属性，默认 True）

    **职责分层**：

    - ``Agent.format_output``：工作流无关，做 typed parsing / 字段抽取
    - ``AgentBaseNode.build_command``：workflow 路由 / state 更新 / goto 决策

    ``call()`` 内部链路：``Agent.run`` → ``format_output`` → ``build_command`` → ``Command``。

    并发约定：实例不可并发复用；workflow 引擎保证同一节点串行。
    turn-internal 状态通过 LangGraph state 而非实例属性传递。
    """

    name: str = "agent_node"
    """Agent 标识。同时充当 ``harness.router.get(name)`` 的 task_type、
    ``MetricsMiddleware`` 的前缀、langfuse span 名等。"""

    cache_graph: bool = True
    """是否缓存编译产物。议价 / Tit-for-Tat 等需要 per-turn 拓扑的场景设 False。"""

    # ── 并发安全：``_reply_streamed`` 走 ContextVar ────────────────────
    #
    # 节点实例在 workflow 引擎中是 **进程级单例**——同一实例可能被多个 asyncio
    # task / 线程并发跑（不同会话同节点）。用 ``ContextVar`` 而非实例属性，
    # per-request 隔离：
    #
    # - ``call()`` 入口 ``set(False)`` 拿 token；finally ``reset(token)`` 保证
    #   退出后回到上层 context 的状态（异常路径也安全）
    # - ``stream_text`` / ``_stream_callback`` 调 ``set(True)`` 写当前 context
    # - 业务代码通过 ``self._reply_streamed`` 读（property 转发 ContextVar.get）
    #   或 ``self._reply_streamed = True / False`` 写（setter 转发 ContextVar.set）
    #
    # ContextVar 在每个 asyncio task 里独立 → 并发 call() 不互相干扰。
    _reply_streamed_var: ClassVar[contextvars.ContextVar[bool]] = contextvars.ContextVar(
        "agent_base_node_reply_streamed", default=False,
    )

    @property
    def _reply_streamed(self) -> bool:
        """本轮 call() 内是否已流式推过文本。读 ContextVar，per-request 隔离。"""
        return self._reply_streamed_var.get()

    @_reply_streamed.setter
    def _reply_streamed(self, value: bool) -> None:
        """兼容业务代码 ``self._reply_streamed = True/False`` 写法。

        ``call()`` 内已用 ``set(False)`` + ``reset(token)`` 做完整生命周期管理，
        本 setter 仅供 turn-internal 局部修改（如 ``stream_text`` / 兜底分支）。
        """
        self._reply_streamed_var.set(value)

    def __init__(self, *, llm: Optional[Any] = None, **kwargs):
        # 先初始化 BaseNode（接受 workflow 节点配置字段如 desc/title/type/...）
        BaseNode.__init__(self, **kwargs)

        # 确保 LLM 工厂 / metric / langfuse 已接入 HARNESS_*（幂等）
        ensure_harness_wired()

        # 业务可能返回 tuple/Sequence；统一转为 list 后再判存在性
        middleware = list(self.build_middleware_for_agent() or [])
        # 仅当业务未显式提供 ConversationHistoryMiddleware 时才注入默认
        # （业务想要 save_turn=True 等定制配置时，自带的实例优先级更高）
        if not any(isinstance(m, ConversationHistoryMiddleware) for m in middleware):
            middleware.insert(0, ConversationHistoryMiddleware(save_turn=False))

        # 再初始化 Agent（接受 model/tools/middleware/graph_builder/harness/...）
        Agent.__init__(
            self,
            model=llm,
            tools=self.build_tools_for_agent(),
            middleware=middleware,
            graph_builder=self.build_graph_builder_for_agent(),
            harness=self.build_harness_for_agent(),
            cache_graph=self.cache_graph,
        )
        # 不再用 self._reply_streamed = False 实例属性——上面的 ContextVar property 接管

    # ───── 5 个可选钩子（默认值兜底） ──────────────────────

    def build_tools_for_agent(self) -> Sequence[Any]:
        """业务工具。默认空。"""
        return []

    def build_middleware_for_agent(self) -> Sequence[AgentMiddleware]:
        """LangChain ``AgentMiddleware`` 链。默认空。

        典型业务装载：

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
        """选择底层 graph 形态。返回 ``None`` 走 ``Agent`` 默认（``ReactGraphBuilder``）。

        - 返回 ``ReactGraphBuilder(...)``：等价于老 ``CreateAgentBaseNode``
        - 返回 ``DeepGraphBuilder(...)``：等价于老 ``DeepAgentBaseNode``
        - 返回 ``CustomGraphBuilder(fn)``：等价于老 ``StateGraphBaseNode``
        """
        return None

    def build_harness_for_agent(self):
        """返回 ``Harness`` 实例；默认 ``default_harness()`` 与全局 HARNESS_* 共享状态。

        单测里业务可返回 ``Harness()`` 构造的独立实例做隔离。
        """
        return default_harness()

    # ───── 抽象钩子：build_command（把 Agent 产物翻译为 Command） ──────────

    @abstractmethod
    def build_command(self, state: GenericState, output: Any) -> Command:
        """把 ``Agent.run`` 返回的产物（经 ``format_output`` 处理）翻译为
        LangGraph ``Command``。

        本方法是 workflow 层的"路由 + state 更新"决策点。``output`` 形态由
        ``format_output`` 决定：

        - 默认（未 override ``format_output``）：``output`` 是 ``str``（messages
          末尾 AI 文本）或 ``output_schema()`` 实例（structured_response 命中）
        - 子类 override ``format_output``：``output`` 可以是任意类型

        典型实现::

            def build_command(self, state, output):
                if isinstance(output, MyOutput):
                    return Command(
                        update={"reply": output.reply, "label": output.label},
                        goto=["next_node"],
                    )
                return Command(update={"reply": str(output)})

        ``Agent`` 本身工作流无关——``Command`` 是 LangGraph 框架特定输出，所以由
        ``AgentBaseNode``（workflow 适配层）持有该抽象。
        """

    # ───── stream_text：桥接到 LangGraph SSE ──────────────

    def stream_text(self, text: str) -> None:
        """workflow 节点流式输出。通过 LangGraph custom stream writer 推到 SSE。

        与老 ``WorkflowAgentNodeMixin.stream_text`` 行为一致，便于业务节点
        在 ``serialize_output`` 之外的位置主动推文本。
        """
        if text:
            # 直接走 ContextVar.set 避开 property 重定向开销
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

    # ───── BaseNode.call → Agent.run → build_command 桥接 ────────────────

    def call(self, state: GenericState, config: Optional[dict] = None) -> Command:
        """workflow 调用入口。

        流程：

        1. ContextVar set/reset(token) 模式锁定本轮 ``_reply_streamed`` 隔离
        2. 从 ``state["sys_query"]`` 取 user query
        3. 构造 ``_stream_callback``，注入 ``RunnableConfig.configurable["stream_callback"]``，
           让 ``Agent.run`` 原生流式（``graph.stream(stream_mode='messages')``）每个
           AIMessageChunk 文本调一次回调
        4. 调 ``Agent.run(state, user_query, config=run_config)`` 拿到 ``format_output``
           处理后的产物（默认透传 = ``str`` 或 ``output_schema`` 实例）
        5. 调 ``self.build_command(state, output)`` 把产物翻译为 ``Command`` 返回
        """
        user_query = state.get("sys_query", "") if hasattr(state, "get") else ""

        # set/reset(token)：本轮 ctx 内强制初始化为 False；call() 退出
        # （正常 return / 异常）时回滚到上层 context 的值，避免脏状态泄漏到下一请求
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

            # Agent.run → format_output 处理过的产物（默认透传）
            output = self.run(state, user_query, config=run_config)
            # 工作流层：把产物翻译为 LangGraph Command
            return self.build_command(state, output)
        finally:
            self._reply_streamed_var.reset(token)


__all__ = ["AgentBaseNode"]
