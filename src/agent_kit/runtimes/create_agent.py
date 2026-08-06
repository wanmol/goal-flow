"""
CreateAgentRuntime：基于 langchain.agents.create_agent 的 AgentRuntime 实现。

定位：最小 tool-calling Agent，无 deepagents 的 planning/subagents/memory/todos 复杂度。
适合：单一目标小节点（分类、提取、改写、合规审查、简单 QA 等）。

底层 API 选择：langchain.agents.create_agent（langchain 0.3+ 官方主推），
与 deepagents 同源——deepagents.create_deep_agent 内部也是基于 create_agent 构建的。

进阶钩子：暴露 response_format()，对应 create_agent(response_format=...)。
其它中间件统一走 middleware_extra()。
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from agent_kit.runtimes.base import AgentRuntime, ResultT


logger = logging.getLogger(__name__)


class CreateAgentRuntime(AgentRuntime[ResultT]):
    """langchain.agents.create_agent 形态的 Runtime。

    与 DeepAgentRuntime 共享 80% 套路（dynamic_prompt + context_schema + checkpointer +
    流式 + 取 reply），区别只在不传 deepagents 特化的 subagents/memory/interrupt_on/todos。

    暴露的进阶钩子：
    - response_format()：结构化响应（与 DeepAgentRuntime 同名 API）
    """

    # ───── 进阶钩子 ──────────────────────────────────

    def response_format(self):
        """返回结构化响应格式（Pydantic class / TypedDict / dict schema），默认 None。"""
        return None

    # ───── _build_graph：委派 ReactGraphBuilder（P4，ADR-003） ────

    def _build_graph(self, *, state=None, system_prompt: str = "", user_content: str = ""):
        """委派 ``ReactGraphBuilder`` 完成图装配。

        P4（ADR-003）：本方法不再直接调 ``langchain.agents.create_agent``，改为
        通过 ``ReactGraphBuilder`` 策略对象。``Runtime``-specific 的 ``response_format()``
        在构造 Builder 时注入，runtime 层的 ``model`` / ``tools`` / ``middleware`` /
        ``context_schema`` 在 ``build()`` 时传入。

        新 ``Agent`` 类的 graph 装配走同一份 ``ReactGraphBuilder``——这消除了
        AgentRuntime / Agent 两套调度对底层 graph API 的双重维护成本。
        """
        from agent_kit.graphs.react import ReactGraphBuilder

        rf = self.response_format()
        builder = ReactGraphBuilder(
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
            f"{type(self).__name__}: create_agent graph created via ReactGraphBuilder "
            f"(response_format={'yes' if rf else 'no'})"
        )
        return graph

    # ───── _execute_graph：流式 + 取结果 ──────────────

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
        ctx = self._build_context(ctx_fields)

        out, _streamed_any = self._stream_agent_messages(
            graph=graph,
            input_msg={"messages": [HumanMessage(content=user_content)]},
            ctx=ctx,
            thread_id=thread_id,
        )

        all_messages = out.get("messages") or []
        result.raw_messages = list(all_messages)

        if "structured_response" in out:
            result.extra["structured_response"] = out["structured_response"]

        result.reply = self._extract_last_reply(all_messages)
