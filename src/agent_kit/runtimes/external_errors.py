"""External dependency error classification -- transport / programming defects vs degradable business parse failures."""
from __future__ import annotations

import json


def is_transport_error(exc: BaseException) -> bool:
    """HTTP timeout / connection failure / 5xx and other infrastructure faults.

    Note: ``requests.HTTPError`` inherits from ``OSError``, so check by status first before falling back.
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
    """Code defects (wrong API call, misspelled attribute name, etc.), must be raised upward to surface as soon as possible.

    For example, passing an unsupported keyword to structlog/logger (``logger.info(..., token=...)``)
    raises a ``TypeError``, which should not be swallowed by business except and downgraded.
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
    """Infrastructure fault or code defect -- neither should be downgraded to a business fallback."""
    return is_transport_error(exc) or is_programming_error(exc)


def reraise_if_critical(exc: BaseException) -> None:
    """transport / programming error → raise upward; a degradable business exception is a noop."""
    if is_critical_error(exc):
        raise exc


def reraise_if_transport_error(exc: BaseException) -> None:
    """Compatible with the old name; new code should use ``reraise_if_critical``."""
    reraise_if_critical(exc)


def is_response_parse_error(exc: BaseException) -> bool:
    """The model/interface returned content, but the format does not match expectations (can warning + downgrade).

    Excludes ``TypeError`` / ``KeyError`` -- those are more likely code bugs, handled by ``reraise_if_critical``.
    """
    return isinstance(exc, (ValueError, json.JSONDecodeError))
