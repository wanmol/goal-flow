"""FallbackReplyMiddleware：异常兜底中间件（替代 ``AgentRuntime.on_failure`` 钩子）。

设计意图：把"LLM 调用抛异常 → 用固定文案兜底"这个模式从 Runtime 钩子下沉为独立的
LangChain ``AgentMiddleware``，依赖 LangChain 中间件协议的 ``wrap_model_call`` 钩子。

与 LangChain 内置 ``ModelFallbackMiddleware`` 的区别：
- ``ModelFallbackMiddleware``：异常时切换到 **另一个 model** 重试
- ``FallbackReplyMiddleware``：异常时直接返回 **固定文案** 不再重试

适用场景：
- LLM 服务降级时给用户兜底友好提示
- 合规拦截后返回标准话术
- 网络失败时返回 "请稍后重试"

**不适用** 的场景（用 ``ModelFallbackMiddleware`` 或 ``ModelRetryMiddleware``）：
- 希望重试或切换模型
- 希望按异常类型分别处理（虽然本中间件也支持 ``on_error`` 回调，但语义偏简单）
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import AIMessage
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState


# on_error(exception) -> 兜底文案
OnErrorFn = Callable[[BaseException], str]


class FallbackReplyMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """异常兜底中间件。

    构造参数：
    - ``fallback_reply``：默认兜底文案，当 ``on_error`` 未提供或抛错时使用
    - ``on_error``：可选回调 ``Callable[[Exception], str]``，按异常类型返回不同文案；
      优先级高于 ``fallback_reply``
    - ``catch``：要捕获的异常类型元组，默认 ``(Exception,)``；不匹配的异常照常抛出

    用法::

        FallbackReplyMiddleware(fallback_reply="出错了，请稍后再试")

        # 按异常类型分支
        FallbackReplyMiddleware(
            fallback_reply="出错了",
            on_error=lambda e: "网络异常" if "timeout" in str(e).lower() else "未知错误",
        )

        # 只捕获网络异常，让其它异常照常抛出
        FallbackReplyMiddleware(
            fallback_reply="网络异常",
            catch=(TimeoutError, ConnectionError),
        )
    """

    def __init__(
        self,
        fallback_reply: str = "请稍后再试。",
        *,
        on_error: Optional[OnErrorFn] = None,
        catch: tuple[type[BaseException], ...] = (Exception,),
    ):
        self._fallback_reply = fallback_reply
        self._on_error = on_error
        self._catch = catch

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        try:
            return handler(request)
        except self._catch as e:
            reply = self._resolve_reply(e)
            return ModelResponse(result=[AIMessage(content=reply)], structured_response=None)

    def _resolve_reply(self, error: BaseException) -> str:
        if self._on_error is None:
            return self._fallback_reply
        try:
            text = self._on_error(error)
        except Exception:
            return self._fallback_reply
        return text or self._fallback_reply
