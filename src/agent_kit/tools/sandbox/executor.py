"""Sandbox code executor: LLM-generated code always runs on a remote sandbox service (never locally).

Layers:
- ``BaseSandboxExecutor``: abstract base class. ``async execute(code) -> (success, output, metadata)``
- ``DifySandboxExecutor``: default implementation, calls the remote dify-sandbox service via HTTP POST

Security / stability constraints (pre-submit interception + output normalization):
- Code length limits: 8 KB for user logic / 512 KB total including injected data
- Plotting library interception: dify-sandbox's seccomp returns EPERM when matplotlib etc. render,
  which the remote side cannot bypass, so intercept before submission and give the model a clear, correctable hint
- Output truncation: ``SANDBOX_OUTPUT_MAX_CHARS`` (default 8192 characters)
- stderr fatality check: pandas/numpy etc. write warnings to stderr but the code did not crash,
  so only treat it as a failure when stderr contains a real exception / syntax error
- Process-level concurrency lane: ``threading.BoundedSemaphore`` limits sandbox concurrency across requests
  (asyncio.Semaphore is bound to a single event loop and cannot cover the cross-thread case)

exit_code convention:
- ``0``  success
- ``1``  code error (service is fine, but user code raised an exception / stderr is fatal)
- ``-1`` timeout
- ``-2`` connection-level / service-level failure
"""
from __future__ import annotations

import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Security constraint constants ──────────────────────────────────────────────────
SANDBOX_TIMEOUT_S: float = float(os.environ.get("SANDBOX_TIMEOUT_S", "15"))
SANDBOX_OUTPUT_MAX_CHARS: int = int(os.environ.get("SANDBOX_OUTPUT_MAX_CHARS", "8192"))
SANDBOX_CODE_MAX_BYTES: int = 8192          # user logic code limit 8 KB
SANDBOX_CODE_TOTAL_MAX_BYTES: int = 524288  # total code limit including injected data 512 KB

# ── Global lane semaphore ──────────────────────────────────────────────
# Limit sandbox concurrency across requests: each request may run on its own thread + own event loop,
# asyncio.Semaphore is bound to a single loop and cannot cover this, so use a process-level threading.BoundedSemaphore.
# Acquisition uses non-blocking polling (50ms); a task cancelled while waiting does not leak a slot.
SANDBOX_MAX_CONCURRENCY: int = int(os.environ.get("SANDBOX_MAX_CONCURRENCY", "4"))
SANDBOX_LANE_WAIT_S: float = float(os.environ.get("SANDBOX_LANE_WAIT_S", "10"))
_GLOBAL_LANE = threading.BoundedSemaphore(SANDBOX_MAX_CONCURRENCY)

# ── Dify sandbox service config (HTTP) ──────────────────────────────────────
DEFAULT_SANDBOX_API_URL = "http://sandbox.dify01:8194/v1/sandbox/run"
DEFAULT_SANDBOX_API_KEY = "dify-sandbox"
SANDBOX_LANGUAGE: str = os.environ.get("SANDBOX_LANGUAGE", "python3")

# Plotting libraries: dify-sandbox's seccomp returns EPERM when importing/rendering matplotlib etc.,
# which the remote service side cannot bypass, so intercept before submission and give the model a clear, correctable hint.
_PLOTTING_LIBS = ("matplotlib", "seaborn", "plotly", "pylab", "pyplot")

# Only treat stderr as a "real failure" when one of the following markers appears (as opposed to pandas/numpy warnings).
_FATAL_STDERR_MARKERS = (
    "Traceback (most recent call last)",
    "SyntaxError",
    "IndentationError",
    "TabError",
)
# Exception-line suffix markers such as "NameError:" / "ValueError:" / "ZeroDivisionError:".
_FATAL_STDERR_SUFFIXES = ("Error:", "Exception:")


def _truncate(text: str, max_chars: int = SANDBOX_OUTPUT_MAX_CHARS) -> str:
    """Truncate output, appending a truncation notice."""
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + (
        f"\n... [输出已截断，共 {len(text)} 字符，仅显示前 {max_chars} 字符]"
    )


def _stderr_is_fatal(stderr: str) -> bool:
    """Determine whether stderr represents a real execution failure (rather than a warning).

    pandas / numpy / urllib3 etc. write ``FutureWarning`` /
    ``DeprecationWarning`` etc. to stderr, but the code did not crash; these should not count as failures.
    Only treat it as fatal when a Traceback / syntax error / ``XxxError:`` / ``XxxException:`` appears.
    """
    if not stderr or not stderr.strip():
        return False
    for marker in _FATAL_STDERR_MARKERS:
        if marker in stderr:
            return True
    # Scan exception lines one by one (avoid false positives like "...Warning: foo Error happened"; only look at the in-line colon marker)
    for line in stderr.splitlines():
        line = line.strip()
        for suffix in _FATAL_STDERR_SUFFIXES:
            idx = line.find(suffix)
            if idx <= 0:
                continue
            # The text before the marker is an identifier fragment (e.g. NameError), and this line is not a warning
            head = line[:idx]
            if head and head[-1].isalpha() and "Warning" not in head:
                return True
    return False


def check_code(code: str) -> Optional[str]:
    """Local validation before submission. Returns an error message string to indicate it should be intercepted; ``None`` means allow it through.

    - Code length limits
    - Plotting library interception (remote seccomp would EPERM, so give a clear hint up front)
    """
    if not code or not code.strip():
        return "[Sandbox] 代码为空，无法执行。"

    raw = code.encode("utf-8")
    if len(raw) > SANDBOX_CODE_TOTAL_MAX_BYTES:
        return (
            f"[Sandbox] 代码过长（{len(raw)} 字节），超过总上限 "
            f"{SANDBOX_CODE_TOTAL_MAX_BYTES} 字节。"
        )

    lowered = code.lower()
    for lib in _PLOTTING_LIBS:
        if lib in lowered:
            return (
                f"[Sandbox] 检测到绘图库 {lib!r}。沙盒环境禁止绘图（seccomp 限制），"
                f"请改为只输出图表所需的数据（如坐标/数值列表），由上层渲染。"
            )
    return None


class _Lane:
    """Context manager for the process-level concurrency lane.

    Acquires a slot via non-blocking polling (50ms), waiting at most ``SANDBOX_LANE_WAIT_S``;
    raises ``TimeoutError`` on timeout. ``__exit__`` releases only after a successful acquisition, avoiding leaks.
    """

    def __init__(self, wait_s: float = SANDBOX_LANE_WAIT_S):
        self._wait_s = wait_s
        self._acquired = False

    def __enter__(self) -> "_Lane":
        deadline = time.monotonic() + self._wait_s
        while True:
            if _GLOBAL_LANE.acquire(blocking=False):
                self._acquired = True
                return self
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"[Sandbox] 并发已满（max={SANDBOX_MAX_CONCURRENCY}），"
                    f"等待 {self._wait_s}s 仍未获取到执行槽位。"
                )
            time.sleep(0.05)

    def __exit__(self, *exc) -> None:
        if self._acquired:
            _GLOBAL_LANE.release()
            self._acquired = False


class BaseSandboxExecutor(ABC):
    """Abstract base class for sandbox executors."""

    @abstractmethod
    async def execute(self, code: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Execute code, returning ``(success, output, metadata)``.

        - ``success=True``  → ``output`` is the stdout content
        - ``success=False`` → ``output`` is the error message
        - ``metadata``      → dict, containing ``executor`` / ``exit_code`` /
          ``execution_time_ms`` / ``stdout_lines`` / ``stderr`` etc.
        """
        ...


class DifySandboxExecutor(BaseSandboxExecutor):
    """Dify sandbox service executor (HTTP).

    Executes code by calling the remote sandbox service via HTTP POST; the service side handles isolation and resource limits::

        POST {api_url}
        headers: {"Content-Type": "application/json", "X-API-Key": <api_key>}
        body:    {"language": "python3", "code": <code>, "stdin": ""}
        resp:    {"code": 0, "data": {"stdout": "...", "stderr"/"error": "..."}}

    Environment variables:
      ``SANDBOX_API_URL``  = http://sandbox.dify01:8194/v1/sandbox/run (default)
      ``SANDBOX_API_KEY``  = dify-sandbox (default)
      ``SANDBOX_LANGUAGE`` = python3 (default)
    """

    def __init__(
        self,
        timeout_s: float = SANDBOX_TIMEOUT_S,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.timeout_s = timeout_s
        self.api_url = (
            api_url or os.environ.get("SANDBOX_API_URL", DEFAULT_SANDBOX_API_URL)
        ).strip()
        self.api_key = api_key or os.environ.get("SANDBOX_API_KEY", DEFAULT_SANDBOX_API_KEY)

    async def execute(self, code: str) -> Tuple[bool, str, Dict[str, Any]]:
        # Local interception before submission (length / plotting libraries)
        blocked = check_code(code)
        if blocked is not None:
            return False, blocked, {
                "executor": "DifySandboxExecutor",
                "exit_code": 1,
                "stdout_lines": 0,
                "stderr": blocked,
            }

        try:
            import httpx
        except ImportError:
            return False, "[Sandbox] DifySandboxExecutor 依赖 httpx，请执行 pip install httpx", {
                "executor": "DifySandboxExecutor",
                "exit_code": -2,
            }

        payload = {"language": SANDBOX_LANGUAGE, "code": code, "stdin": ""}
        headers = {"Content-Type": "application/json", "X-API-Key": self.api_key}

        t0 = time.monotonic()
        logger.info(
            "[DifySandbox] POST %s (language=%s, timeout=%ss)",
            self.api_url, SANDBOX_LANGUAGE, self.timeout_s,
        )

        # Process-level concurrency lane: exceeding concurrency raises TimeoutError → normalized to a connection-level failure
        try:
            lane = _Lane()
            lane.__enter__()
        except TimeoutError as e:
            return False, str(e), {
                "executor": "DifySandboxExecutor",
                "exit_code": -2,
                "stdout_lines": 0,
                "stderr": str(e),
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s + 5) as client:
                resp = await client.post(self.api_url, json=payload, headers=headers)
        except Exception as e:
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.error(
                "[DifySandbox] 连接失败 (%s): %s (elapsed=%.0fms)",
                type(e).__name__, e, elapsed_ms,
            )
            return False, f"[Sandbox] 沙盒服务连接失败: {e}", {
                "executor": "DifySandboxExecutor",
                "exit_code": -2,
                "execution_time_ms": elapsed_ms,
                "stdout_lines": 0,
                "stderr": str(e),
            }
        finally:
            lane.__exit__(None, None, None)

        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

        if resp.status_code != 200:
            logger.error("[DifySandbox] HTTP %s: %s", resp.status_code, resp.text[:300])
            return False, f"[Sandbox] 沙盒服务返回 HTTP {resp.status_code}: {resp.text[:500]}", {
                "executor": "DifySandboxExecutor",
                "exit_code": -2,
                "execution_time_ms": elapsed_ms,
                "stdout_lines": 0,
                "stderr": resp.text[:500],
            }

        try:
            result = resp.json()
        except Exception as e:
            return False, f"[Sandbox] 沙盒服务响应非 JSON: {e}（{resp.text[:300]}）", {
                "executor": "DifySandboxExecutor",
                "exit_code": -2,
                "execution_time_ms": elapsed_ms,
                "stdout_lines": 0,
                "stderr": resp.text[:500],
            }

        data = result.get("data") or {}
        stdout = data.get("stdout") or ""
        stderr = data.get("stderr") or data.get("error") or ""
        # Service-side code != 0 → service/request-level failure (exit_code=-2); error details are usually in result["message"].
        service_ok = result.get("code", 0) in (0, None)
        service_msg = "" if service_ok else str(result.get("message") or "").strip()
        # stderr may only be a warning; only treat it as a failure when it contains a real exception/syntax error.
        success = service_ok and not _stderr_is_fatal(stderr)

        if success:
            output = stdout
        elif not service_ok:
            output = service_msg or (stdout + "\n" + stderr).strip() or stderr
        else:
            output = (stdout + "\n" + stderr).strip() if stdout else stderr

        return success, _truncate(output), {
            "executor": "DifySandboxExecutor",
            "exit_code": 0 if success else (1 if service_ok else -2),
            "execution_time_ms": elapsed_ms,
            "stdout_lines": stdout.count("\n") + 1 if stdout.strip() else 0,
            "stderr": _truncate(stderr or service_msg, 500),
        }
