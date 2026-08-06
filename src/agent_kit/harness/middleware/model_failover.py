"""ModelFailoverMiddleware：主备模型切换中间件。

设计意图：主模型「不可用」时自动切换到备选模型重试。依赖 LangChain 中间件协议的
``wrap_model_call`` 钩子——它包裹真实 LLM 调用，可捕获异常并用
``request.override(model=backup)`` 换模型重试。

「不可用」的定义（默认 ``should_failover``）：
- 基础设施故障：超时 / 连接失败 / HTTP 5xx（复用 ``external_errors.is_transport_error``）
- 限流：HTTP 429 / ``RateLimitError``

**不属于「不可用」**（默认不切换，异常原样上抛）：
- 敏感词 / 内容审核拦截（通常表现为 ``ValueError`` / ``ContentFilterFinishReasonError``
  / 业务返回码）——切换备选无意义，备选同样会被拦
- 编程错误（``TypeError`` / ``AttributeError`` 等）——应尽快暴露

与相邻中间件的分工：
- ``ModelFailoverMiddleware``：异常时切到 **另一个 model** 重试（本文件）
- ``FallbackReplyMiddleware``：异常时返回 **固定文案** 不再重试
- 二者可组合——failover 在外层，全部备选挂掉后抛出，由内层 fallback 接住::

      middleware=[
          ModelFailoverMiddleware(backup_model),
          FallbackReplyMiddleware("服务繁忙，请稍后再试"),
      ]
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState
from agent_kit.runtimes.external_errors import (
    is_programming_error,
    is_transport_error,
)

logger = logging.getLogger(__name__)


# should_failover(exception) -> 是否切换到备选模型
FailoverPredicate = Callable[[BaseException], bool]


def _is_rate_limit_error(exc: BaseException) -> bool:
    """限流识别。

    不硬依赖 openai：优先按类名 ``RateLimitError`` 匹配，再按
    ``status_code == 429`` 兜底（兼容 ``openai.APIStatusError`` /
    ``requests.HTTPError`` 等带 status 的异常）。
    """
    if type(exc).__name__ == "RateLimitError":
        return True
    # openai.APIStatusError 把 status_code 挂在异常上
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    # requests.HTTPError：status 在 response 上
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 429:
        return True
    return False


def default_should_failover(exc: BaseException) -> bool:
    """默认「不可用」判定：基础设施故障 + 限流才切换。

    编程错误绝不切换（应尽快暴露）；敏感词等业务异常（``ValueError`` 等）
    不属于「不可用」，返回 ``False`` → 异常原样上抛。
    """
    if is_programming_error(exc):
        return False
    return is_transport_error(exc) or _is_rate_limit_error(exc)


class ModelFailoverMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """主备模型切换中间件。

    构造参数：
    - ``*backups``：一个或多个 **已实例化** 的备选 ``BaseChatModel``，按顺序降级。
      主模型来自 ``request.model``，无需重复传入。
    - ``should_failover``：``Callable[[BaseException], bool]``，返回 ``True`` 才切换。
      默认 ``default_should_failover``（基础设施故障 + 限流）。

    行为：
    - 主模型成功 → 直接返回，不碰备选
    - 主模型抛出且 ``should_failover(exc)`` 为 ``True`` → 切下一个备选重试
    - ``should_failover(exc)`` 为 ``False``（如敏感词）→ 异常原样上抛，不切换
    - 主 + 所有备选全部挂掉 → 抛出最后一次异常（交给后续中间件兜底）

    用法::

        ModelFailoverMiddleware(backup_model)
        ModelFailoverMiddleware(backup_a, backup_b)  # 多级降级
        ModelFailoverMiddleware(
            backup_model,
            should_failover=lambda e: "overloaded" in str(e).lower(),
        )
    """

    def __init__(
        self,
        *backups: Any,
        should_failover: Optional[FailoverPredicate] = None,
    ):
        if not backups:
            raise ValueError(
                "ModelFailoverMiddleware: at least one backup model is required"
            )
        self._backups = list(backups)
        self._should_failover = should_failover or default_should_failover

    def _models(self, request: ModelRequest) -> list[Any]:
        """主模型 + 备选，按尝试顺序。"""
        return [request.model, *self._backups]

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        models = self._models(request)
        last_exc: Optional[BaseException] = None
        for i, model in enumerate(models):
            try:
                req = request if i == 0 else request.override(model=model)
                return handler(req)
            except Exception as e:
                last_exc = e
                if not self._should_failover(e):
                    # 业务异常（敏感词等）/ 编程错误 → 不切换，原样上抛
                    raise
                if i == len(models) - 1:
                    # 已是最后一个备选，无可降级 → 抛出，交给后续中间件兜底
                    logger.warning(
                        "ModelFailoverMiddleware: all %d model(s) unavailable; "
                        "raising last error (%r)",
                        len(models),
                        e,
                    )
                    raise
                logger.warning(
                    "ModelFailoverMiddleware: model[%d] unavailable (%r); "
                    "failing over to backup[%d]",
                    i,
                    e,
                    i,
                )
        # 理论不可达（循环要么 return 要么 raise）
        assert last_exc is not None
        raise last_exc

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> ModelResponse:
        models = self._models(request)
        last_exc: Optional[BaseException] = None
        for i, model in enumerate(models):
            try:
                req = request if i == 0 else request.override(model=model)
                return await handler(req)
            except Exception as e:
                last_exc = e
                if not self._should_failover(e):
                    raise
                if i == len(models) - 1:
                    logger.warning(
                        "ModelFailoverMiddleware: all %d model(s) unavailable; "
                        "raising last error (%r)",
                        len(models),
                        e,
                    )
                    raise
                logger.warning(
                    "ModelFailoverMiddleware: model[%d] unavailable (%r); "
                    "failing over to backup[%d]",
                    i,
                    e,
                    i,
                )
        assert last_exc is not None
        raise last_exc
