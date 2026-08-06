"""Agent：新公开入口（替代 ``AgentRuntime``）。

设计意图（ADR-003）：
- 把 ``AgentRuntime`` 的 12 钩子压缩到 4 个抽象 + 2 个可选
- 所有"切面"（短路、跳过 LLM、敏感词、历史、兜底、流式、metrics、langfuse、skills）
  通过外部传 ``middleware=[...]`` 接入
- 三个底层 graph API（``create_agent`` / ``create_deep_agent`` / 自定义 graph）
  改为 ``GraphBuilder`` 策略对象，构造时注入
- 治理依赖（LLM 路由 / Prompt 注册表 / Tracer / Profiles）通过 ``Harness`` 实例
  显式注入，不再依赖全局单例

老 ``AgentRuntime`` 继续可用（P2 已加 DeprecationWarning）。两套 API 并存。

最小用法（Agent 本身工作流无关，``run()`` 返回 ``format_output`` 的产物）::

    class MyAgent(Agent[MyOutput]):
        name = "my_classifier"

        def output_schema(self):
            return MyOutput

        def build_prompt(self, state):
            return "你是一个分类器。"

        # format_output 默认透传；若要 typed parsing 等可选 override
        # def format_output(self, state, output): return output

    agent = MyAgent(model="qwen-plus", tools=[my_tool])
    output = agent.run({}, "我要找税务筹划公司")
    # output 是 MyOutput 实例（structured_response 命中）或 str（messages 末尾文本）

工作流场景（继承 ``node.agent_base.AgentBaseNode``）::

    class MyNode(AgentBaseNode[MyOutput]):
        name = "my_classifier"
        def output_schema(self): return MyOutput
        def build_prompt(self, state): return "你是一个分类器。"
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


# 默认 thread_id —— 业务通常会通过 RunnableConfig 提供
_DEFAULT_THREAD_ID = "agent_default"


def _extract_text(content: Any) -> str:
    """归一化消息 content 为 plain str（兼容 list-of-dict 形态）。"""
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
    """从消息流末尾找最后一条非 tool_call 的 AI 文本作为 reply。"""
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

# 不支持 AsyncSubAgent，CompiledSubAgent；  目前只有 SubAgent 支持middleware， subagent需要通过middleware初始化上下文隔离功能
_SubAgentType = SubAgent 
#_SubAgentType = SubAgent | CompiledSubAgent | AsyncSubAgent


class Agent(ABC, Generic[OutputT]):
    """统一 Agent 入口（工作流无关）。

    子类必须实现：
    - ``output_schema() -> type[BaseModel]``：声明结构化输出形态
    - ``build_prompt(state) -> str``：构造 system prompt

    可选 override：
    - ``format_user_input(state, query) -> str``：自定义 user 消息体；默认透传 ``query``
    - ``format_output(state, output) -> Any``：格式化 graph 原始输出；默认透传

    把"翻译为 Command / dict / 其它框架特定输出"留给工作流适配层（如
    ``node.agent_base.AgentBaseNode.build_command``），保持 Agent 本身可独立测试、
    可在非 workflow 场景使用。

    所有"切面"行为（短路、跳过、兜底、流式、metrics、历史、敏感词、skills）
    都通过 ``middleware=[...]`` 注入，不再是钩子。
    """

    name: str = "agent"
    """Agent 标识；同时充当 ``harness.router.get(name)`` 的 task_type、metric 前缀等。"""

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
        """构造一个 Agent 实例。

        :param model: LLM 实例 / 模型名字符串 / None。
            - ``None`` 且 ``harness`` 已提供：从 ``harness.router.get(self.name)`` 拿
            - ``str``：通过 ``langchain.chat_models.init_chat_model`` 实例化
            - 其它：当作 ``BaseChatModel`` 直接用
        :param tools: 业务工具（``BaseTool`` 实例）
        :param middleware: 中间件链；执行顺序按列表顺序
        :param graph_builder: ``GraphBuilder`` 实例；默认 ``ReactGraphBuilder()``
        :param harness: ``Harness`` 实例；用于 LLM 路由 + 治理能力注入
        :param cache_graph: 是否复用编译产物。``True`` 时 graph 只构建一次
        """
        self._model = model
        self._tools = list(tools)
        self._middleware = list(middleware)
        self._graph_builder = graph_builder
        self._harness = harness
        self._cache_graph = cache_graph
        self._compiled: Optional[Any] = None
        self._subagents = list(subagents or [])

    # ───── 子类必须实现的 3 个抽象钩子 ───────────────────

    @abstractmethod
    def output_schema(self) -> type[OutputT]:
        """声明本 Agent 的结构化输出形态。``ReactGraphBuilder`` /
        ``DeepGraphBuilder`` 会把这个 schema 传给 ``response_format`` 参数。
        """

    @abstractmethod
    def build_prompt(self, state: Any) -> str:
        """构造 system prompt。每次 run 时调用一次。"""

    # ───── 可选 override（默认实现透传） ─────────────────

    def format_user_input(self, state: Any, query: str) -> str:
        """格式化用户输入为发给 LLM 的 message 内容。默认透传。"""
        return query

    def format_output(self, state: Any, output: Any) -> Any:
        """格式化 graph 原始输出。默认透传——返回 ``output`` 原样。

        ``output`` 可能是：
        - ``output_schema()`` 的实例（如果 graph 启用了 structured_response）
        - 普通字符串（最后一条 AI 文本回复）

        子类可 override 做 typed parsing、字段抽取、post-process 等。

        **不再把"翻译为 Command"作为 Agent 的职责** —— 工作流层（如
        ``AgentBaseNode.build_command``）负责把 ``format_output`` 的产物翻译为
        框架特定的输出（``Command`` / ``dict`` / 其它）。Agent 本身保持工作流无关。
        """
        return output

    # ───── 内部：model / graph 解析 ──────────────────────

    def _resolve_model(self) -> Any:
        """三态解析 model：直接传入 > model 字符串 > harness.router.get(name)。"""
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
        
        # 如果有 subagents，强制使用 DeepGraphBuilder， 只有deepagent支持subagents
        if self._subagents:
            for subagent in self._subagents:
                if not isinstance(subagent, _SubAgentType):
                    raise ValueError(
                        f"Agent {self.name!r}: subagents must be _SubAgentType instances"
                    )
                
                sub_middleware = subagent.get("middleware", [])
                # 插入 SubAgentInitializeMiddleware 到 middleware 首位, 初始化子agent的messages参数
                sub_middleware.insert(0, SubAgentInitializeMiddleware())
                subagent["middleware"] = sub_middleware
                
            return DeepGraphBuilder(
                subagents=self._subagents,
            )
    
        # 默认 ReactGraphBuilder（最常用）
        return ReactGraphBuilder()

    def _compile(self) -> Any:
        """编译 graph；按 ``cache_graph`` 决定复用。"""
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
        """手动清编译缓存；下次 ``_compile`` 时重建。"""
        self._compiled = None

    # ───── 执行入口 ──────────────────────────────────────

    def run(
        self,
        state: Any,
        user_query: str,
        *,
        config: Optional[dict] = None,
    ) -> Any:
        """执行一次 agent 调用。返回 ``format_output`` 的产物（默认透传 graph 输出）。

        执行流程：
        1. ``build_prompt(state)`` 构造 system prompt（middleware 可覆盖）
        2. ``format_user_input(state, user_query)`` 构造 user 消息体
        3. ``_compile()`` 拿到 CompiledGraph
        4. **``graph.stream(stream_mode='messages')`` 逐 chunk 驱动**——每个
           ``AIMessageChunk`` 的文本内容通过 ``RunnableConfig.configurable["stream_callback"]``
           推送（业务通过 ``AgentBaseNode`` 自动注入或在 ``config`` 里显式设）
        5. 流结束后用 ``graph.get_state(config).values`` 拿终态
        6. ``format_output(state, output)`` 返回最终产物

        返回值形态：
        - 默认：``str``（messages 末尾 AI 回复）或 ``output_schema()`` 的实例
        - ``format_output`` 被 override：子类决定

        把"翻译为 Command/dict 等框架特定输出"的职责留给工作流层
        （如 ``AgentBaseNode.build_command``），Agent 本身保持工作流无关。
        """
        graph = self._compile()
        system_prompt = self.build_prompt(state)
        user_content = self.format_user_input(state, user_query)

        # 把 system_prompt 暂存到 RunnableConfig 的 context（ReactGraphBuilder
        # 期望从 runtime.context.system_prompt 读，与 DynamicPromptMiddleware 协议一致）
        run_config: dict = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        # 兼容老的 thread_id 概念（LangGraph checkpointer 需要）
        configurable.setdefault("thread_id", f"{self.name}__{_DEFAULT_THREAD_ID}")
        run_config["configurable"] = configurable

        input_state = {
            "messages": [HumanMessage(content=user_content)],
            # 把 system_prompt 也放进 state，给 middleware（如 DynamicPromptMiddleware）使用
            "system_prompt": system_prompt,
        }
        if hasattr(state, "get"):
            for k in ("sys_conversation_id", "sys_user_id"):
                v = state.get(k)
                if v is not None:
                    input_state[k] = v

        # 流式调度：每个 AIMessageChunk 推送给 stream_callback（业务可选）
        stream_callback = configurable.get("stream_callback")
        for chunk, _ in graph.stream(
            input_state, config=run_config, stream_mode="messages"
        ):
            if stream_callback is None or not isinstance(chunk, AIMessageChunk):
                continue
            chunk : AIMessageChunk = chunk
            response_metadata : dict = chunk.response_metadata
            # 跳过纯 tool_call 块（无文本内容）
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

        # 流结束后取终态
        result_state = graph.get_state(run_config).values

        # 优先用 structured_response；否则用 messages 末尾的 AI 回复
        output = result_state.get("structured_response")
        if output is None:
            output = _extract_last_reply(result_state.get("messages") or [])
        return self.format_output(state, output)
