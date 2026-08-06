"""
StateGraphRuntime：基于手动 StateGraph 的 AgentRuntime 实现。

定位：完全自定义状态机（多步骤、多分支、多 LLM 调用），子类自己拼 graph。
适合：议价节点（Tit-for-Tat 多轮）、复核流水线（拆解→并行评估→汇总）等。

子类必须实现一个额外钩子：
- build_state_graph(*, state=None, system_prompt="", user_content="") -> StateGraph
  返回未 compile 的 langgraph.graph.StateGraph

StateGraphRuntime 负责：
- compile graph 并装配 checkpointer
- 流式驱动 + 取 reply（按子类约定的 state key）
- 与其它 Runtime 共享同一套 AgentRuntime 协议（钩子、make_tool、错误归类）

State Key 约定：
- StateGraph 的 input/output 必须含 ``messages: list``（与 langgraph 主流约定一致）
- 最后一条 AI message 的 content 作为 result.reply
- 子类有特殊数据可通过 ``state_to_extra(out_state)`` 钩子塞到 result.extra
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage

from agent_kit.runtimes.base import AgentRuntime, ResultT


logger = logging.getLogger(__name__)


class StateGraphRuntime(AgentRuntime[ResultT]):
    """手动 StateGraph 形态的 Runtime。

    比 DeepAgent / CreateAgent 灵活——子类完全控制状态机；
    但样板代码也最多——子类要自己定义 state schema、节点函数、边。

    StateGraphRuntime 只承担：
    - checkpointer 装配 + thread_id 隔离
    - 流式逐 token 透传
    - reply / raw_messages 提取
    - 错误归类 + metric/stream callback 注入（继承自 AgentRuntime）
    """

    @abstractmethod
    def build_state_graph(
        self,
        *,
        state: Any = None,
        system_prompt: str = "",
        user_content: str = "",
    ):
        """构造并返回未 compile 的 ``langgraph.graph.StateGraph``。

        ``state/system_prompt/user_content`` 仅在 ``cache_graph=False`` 时由
        Runtime 透传过来；缓存模式下为占位空值（None / ""）。子类如果不依赖
        per-turn 信息，可以忽略这三个参数。
        """

    def state_to_extra(self, out_state: dict) -> dict:
        """把 graph 终态 dict 翻译成 result.extra（默认 empty）。"""
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
            ctx=None,  # StateGraph 没有 context_schema
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
