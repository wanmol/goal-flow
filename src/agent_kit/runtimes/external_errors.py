"""外部依赖错误分类 — transport / 编程缺陷 vs 可降级的业务解析失败。"""
from __future__ import annotations

import json


def is_transport_error(exc: BaseException) -> bool:
    """HTTP 超时/连接失败/5xx 等基础设施故障。

    注意：``requests.HTTPError`` 继承自 ``OSError``，必须先按 status 判断再兜底。
    """
    try:
        import requests

        if isinstance(exc, requests.HTTPError):
            resp = getattr(exc, "response", None)
            return resp is not None and resp.status_code >= 500
        if isinstance(exc, requests.Timeout | requests.ConnectionError):
            return True
    except ImportError:
        pass
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return False


def is_programming_error(exc: BaseException) -> bool:
    """代码缺陷（错误 API 调用、属性名拼错等），必须向上抛以便尽快暴露。

    例如 structlog/logger 传入不支持的 keyword（``logger.info(..., token=...)``）
    会抛 ``TypeError``，不应被业务 except 吞掉后降级。
    """
    return isinstance(
        exc,
        (
            TypeError,
            AttributeError,
            NameError,
            NotImplementedError,
            ImportError,
            AssertionError,
        ),
    )


def is_critical_error(exc: BaseException) -> bool:
    """基础设施故障或编程缺陷 — 均不应降级为业务 fallback。"""
    return is_transport_error(exc) or is_programming_error(exc)


def reraise_if_critical(exc: BaseException) -> None:
    """transport / 编程错误 → 向上抛；可降级的业务异常则 noop。"""
    if is_critical_error(exc):
        raise exc


def reraise_if_transport_error(exc: BaseException) -> None:
    """兼容旧名；新代码请用 ``reraise_if_critical``。"""
    reraise_if_critical(exc)


def is_response_parse_error(exc: BaseException) -> bool:
    """模型/接口返回了内容，但格式不符合预期（可 warning + 降级）。

    不含 ``TypeError`` / ``KeyError`` — 那些更可能是代码 bug，走 ``reraise_if_critical``。
    """
    return isinstance(exc, (ValueError, json.JSONDecodeError))
