"""
DeepAgentRuntime：基于 deepagents.create_deep_agent 的 AgentRuntime 实现。

继承 AgentRuntime 后只需实现：
- _build_graph()：调 create_deep_agent + 装配 4 个进阶钩子（subagents/memory/interrupt_on/response_format）
- _execute_graph()：跑 graph.stream + 取 raw_messages / todos / reply

deepagents 独有的 4 个进阶钩子（subagents / memory / interrupt_on / response_format）
作为 DeepAgentRuntime 的扩展接口暴露，业务子类按需重写。
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from agent_kit.runtimes.base import AgentRuntime, ResultT


logger = logging.getLogger(__name__)


class DeepAgentRuntime(AgentRuntime[ResultT]):
    """deepagents 形态的 Runtime。

    在 AgentRuntime 12 个共享钩子的基础上，额外暴露 4 个 deepagents 独有的进阶钩子：
    - build_subagents()：并发 Sub-agent
    - memory_keys()：启动时加载到 prompt 的 AGENTS.md 路径
    - interrupt_on_tools()：工具调用前 HITL 中断
    - response_format()：结构化响应格式

    默认全部返回空，业务子类按需重写。
    """

    # ───── 4 个 deepagents 独有的进阶钩子 ──────────────

    def build_subagents(self) -> list:
        """返回 deepagents subagents 列表（SubAgent / CompiledSubAgent / AsyncSubAgent）。"""
        return []

    def memory_keys(self) -> list[str]:
        """返回需要在启动时加载到 system prompt 的 AGENTS.md 路径列表。"""
        return []

    def interrupt_on_tools(self) -> dict:
        """返回需要 HITL 中断的工具名映射（dict[tool_name, InterruptOnConfig | bool]）。"""
        return {}

    def response_format(self):
        """返回结构化响应格式（Pydantic class / TypedDict / dict schema），默认 None。"""
        return None

    # ───── _build_graph：委派 DeepGraphBuilder（P4，ADR-003） ─────

    def _build_graph(self, *, state=None, system_prompt: str = "", user_content: str = ""):
        """委派 ``DeepGraphBuilder`` 完成图装配。

        P4（ADR-003）：本方法不再直接调 ``deepagents.create_deep_agent``，改为
        通过 ``DeepGraphBuilder`` 策略对象。``Runtime``-specific 的 4 个钩子
        （``build_subagents`` / ``memory_keys`` / ``interrupt_on_tools`` /
        ``response_format``）在构造 Builder 时注入。

        新 ``Agent`` 类的 graph 装配走同一份 ``DeepGraphBuilder``——这消除了
        AgentRuntime / Agent 两套调度对底层 graph API 的双重维护成本。
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

    # ───── _execute_graph 实现：流式 + 取结果 ─────────

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
