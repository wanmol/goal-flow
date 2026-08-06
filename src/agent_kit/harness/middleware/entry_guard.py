"""EntryGuardMiddleware：入口短路中间件（替代 ``AgentRuntime.before_call`` 钩子）。

设计意图：把"入口预检失败 → 直接返回固定回复"这个常见模式从 Runtime 钩子下沉为
独立的 LangChain ``AgentMiddleware``，使其可以：

- 跨 Agent 复用（一份 predicate 用在多个 Agent 上）
- 独立 import、独立测试、独立组合（与其它 middleware 顺序可控）
- 与 LangChain 中间件生态（``ContextMiddleware`` / ``SensitiveCheckMiddleware`` 等）风格统一

适用场景：
- 状态预检失败 → 直接回固定提示
- 用户身份未认证 → 拒绝
- 业务前置条件未满足 → 提示用户补充信息

**不适用** 的场景（继续用 ``before_call`` 钩子）：
- 需要 ``Command(goto="some_node")`` 跳转到具体节点（本中间件只能 ``jump_to=["end"]``）
- 需要在短路时 ``update`` 多个 state 字段（中间件只更新 messages）

与 ``before_call`` 钩子的对应关系：

    # 老写法（钩子）
    def before_call(self, state):
        if not state.get("category"):
            return Command(update={"reply": "请先选择类目"})
        return None

    # 新写法（中间件）
    EntryGuardMiddleware(
        lambda state, runtime:
            ("end", "请先选择类目") if not state.get("category") else None
    )
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


# predicate 返回 (jump_to, reply_text) 触发短路；返回 None 继续正常流程
GuardResult = Optional[Tuple[str, str]]
GuardPredicate = Callable[[ContextAgentState, "Runtime[Any]"], GuardResult]


class EntryGuardMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """入口短路中间件。

    构造时传入 ``predicate(state, runtime) -> (jump_to, reply) | None``：

    - 返回 ``None``：放行，继续后续 middleware / agent loop
    - 返回 ``("end", "兜底文案")``：短路到 end，把 ``AIMessage(content="兜底文案")``
      作为最终回复写入 messages
    """

    def __init__(self, predicate: GuardPredicate):
        self._predicate = predicate

    @override
    @hook_config(can_jump_to=["end"])
    def before_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        result = self._predicate(state, runtime)
        if result is None:
            return None
        jump_to, reply = result
        return {"jump_to": jump_to, "messages": [AIMessage(content=reply)]}

    @override
    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)
