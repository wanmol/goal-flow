"""ModelSkipMiddleware：跳过 LLM 调用中间件（替代 ``AgentRuntime.should_run_agent`` 钩子）。

设计意图：把"低信号 ack / 缓存命中 / 业务侧已收集到全部信息 → 不调 LLM 直接出回复"
这个模式从 Runtime 钩子下沉为独立的 LangChain ``AgentMiddleware``。

与 ``EntryGuardMiddleware`` 的区别：
- ``EntryGuardMiddleware`` 在 ``before_agent`` 触发，**早于** agent loop
- ``ModelSkipMiddleware`` 在 ``before_model`` 触发，**进入** agent loop 但跳过 LLM

适用场景：
- 用户输入是 "好"/"嗯"/"ok" 等无信号 ack，省 LLM 成本
- 缓存命中，直接返回缓存回复
- 业务侧已通过其它路径收集到全部所需信息，无需再 LLM 决策

**不适用** 的场景（继续用 ``should_run_agent`` 钩子）：
- 需要 ``result.failed = True`` / 走 ``finalize`` 完整后处理流程
- 需要写多个非 messages 的 state 字段
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT, hook_config
from langchain_core.messages import AIMessage
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


# predicate 返回 (skip_reason, reply_text) 触发跳过；返回 None 继续调 LLM
SkipResult = Optional[Tuple[str, str]]
SkipPredicate = Callable[[ContextAgentState, "Runtime[Any]"], SkipResult]


class ModelSkipMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """跳过 LLM 调用中间件。

    构造时传入 ``predicate(state, runtime) -> (skip_reason, reply) | None``：

    - 返回 ``None``：放行，正常调 LLM
    - 返回 ``("cached", "你已确认订单")``：跳过 LLM，把 ``AIMessage(content=reply)``
      作为模型回复写入 messages，结束 agent loop

    ``skip_reason`` 仅用于日志/调试，不影响行为。
    """

    def __init__(self, predicate: SkipPredicate):
        self._predicate = predicate

    @override
    @hook_config(can_jump_to=["end"])
    def before_model(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        result = self._predicate(state, runtime)
        if result is None:
            return None
        _reason, reply = result
        return {"jump_to": "end", "messages": [AIMessage(content=reply)]}

    @override
    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        return self.before_model(state, runtime)
