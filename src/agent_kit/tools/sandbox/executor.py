"""沙盒代码执行器：LLM 生成的代码统一走远端沙盒服务执行（不在本地执行）。

层次：
- ``BaseSandboxExecutor``：抽象基类。``async execute(code) -> (success, output, metadata)``
- ``DifySandboxExecutor``：默认实现，HTTP POST 调用远端 dify-sandbox 服务

安全 / 稳定性约束（提交前拦截 + 输出归一化）：
- 代码长度上限：用户逻辑 8 KB / 含注入数据总量 512 KB
- 绘图库拦截：dify-sandbox 的 seccomp 会在 matplotlib 等出图时返回 EPERM，
  远端无法绕过，故提交前拦截，给模型清晰可纠正的提示
- 输出截断：``SANDBOX_OUTPUT_MAX_CHARS``（默认 8192 字符）
- stderr 致命性判定：pandas/numpy 等会往 stderr 写 warning 但代码没崩，
  仅当 stderr 含真正的异常/语法错误时才判失败
- 进程级并发 lane：``threading.BoundedSemaphore`` 跨请求限制 sandbox 并发
  （asyncio.Semaphore 绑定单事件循环管不住跨线程场景）

exit_code 约定：
- ``0``  成功
- ``1``  代码出错（服务正常，但用户代码抛异常 / stderr 致命）
- ``-1`` 超时
- ``-2`` 连接级 / 服务级失败
"""
from __future__ import annotations

import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ── 安全约束常量 ──────────────────────────────────────────────────
SANDBOX_TIMEOUT_S: float = float(os.environ.get("SANDBOX_TIMEOUT_S", "15"))
SANDBOX_OUTPUT_MAX_CHARS: int = int(os.environ.get("SANDBOX_OUTPUT_MAX_CHARS", "8192"))
SANDBOX_CODE_MAX_BYTES: int = 8192          # 用户逻辑代码上限 8 KB
SANDBOX_CODE_TOTAL_MAX_BYTES: int = 524288  # 含注入数据的总代码上限 512 KB

# ── 全局 lane 信号量 ──────────────────────────────────────────────
# 跨请求限制 sandbox 并发：每个请求可能跑在独立线程+独立事件循环，
# asyncio.Semaphore 绑定单循环管不住，故用进程级 threading.BoundedSemaphore。
# 获取走非阻塞轮询（50ms），等待中任务被取消不会泄漏槽位。
SANDBOX_MAX_CONCURRENCY: int = int(os.environ.get("SANDBOX_MAX_CONCURRENCY", "4"))
SANDBOX_LANE_WAIT_S: float = float(os.environ.get("SANDBOX_LANE_WAIT_S", "10"))
_GLOBAL_LANE = threading.BoundedSemaphore(SANDBOX_MAX_CONCURRENCY)

# ── Dify 沙盒服务配置（HTTP）──────────────────────────────────────
DEFAULT_SANDBOX_API_URL = "http://sandbox.dify01:8194/v1/sandbox/run"
DEFAULT_SANDBOX_API_KEY = "dify-sandbox"
SANDBOX_LANGUAGE: str = os.environ.get("SANDBOX_LANGUAGE", "python3")

# 绘图库：dify-sandbox 的 seccomp 会在 matplotlib 等导入/出图时返回 EPERM，
# 远端服务侧无法绕过，因此直接在提交前拦截，给模型一个清晰可纠正的提示。
_PLOTTING_LIBS = ("matplotlib", "seaborn", "plotly", "pylab", "pyplot")

# stderr 中出现下列标志才判定为「真正失败」（区别于 pandas/numpy 的 warning）。
_FATAL_STDERR_MARKERS = (
    "Traceback (most recent call last)",
    "SyntaxError",
    "IndentationError",
    "TabError",
)
# 形如 "NameError:" / "ValueError:" / "ZeroDivisionError:" 的异常行尾标志。
_FATAL_STDERR_SUFFIXES = ("Error:", "Exception:")


def _truncate(text: str, max_chars: int = SANDBOX_OUTPUT_MAX_CHARS) -> str:
    """输出截断，附带截断提示。"""
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + (
        f"\n... [输出已截断，共 {len(text)} 字符，仅显示前 {max_chars} 字符]"
    )


def _stderr_is_fatal(stderr: str) -> bool:
    """判断 stderr 是否代表真正的执行失败（而非 warning）。

    pandas / numpy / urllib3 等会往 stderr 写 ``FutureWarning`` /
    ``DeprecationWarning`` 等，但代码并未崩溃；这类不应判失败。
    仅当出现 Traceback / 语法错误 / ``XxxError:`` / ``XxxException:`` 才判致命。
    """
    if not stderr or not stderr.strip():
        return False
    for marker in _FATAL_STDERR_MARKERS:
        if marker in stderr:
            return True
    # 逐行扫描异常行（避免 "...Warning: foo Error happened" 这类误判，只看行内冒号标志）
    for line in stderr.splitlines():
        line = line.strip()
        for suffix in _FATAL_STDERR_SUFFIXES:
            idx = line.find(suffix)
            if idx <= 0:
                continue
            # 标志前是标识符片段（如 NameError），且这一行不是 warning
            head = line[:idx]
            if head and head[-1].isalpha() and "Warning" not in head:
                return True
    return False


def check_code(code: str) -> Optional[str]:
    """提交前的本地校验。返回错误提示字符串表示应拦截；``None`` 表示放行。

    - 代码长度上限
    - 绘图库拦截（远端 seccomp 会 EPERM，提前给清晰提示）
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
    """进程级并发 lane 的上下文管理器。

    非阻塞轮询获取槽位（50ms），最多等待 ``SANDBOX_LANE_WAIT_S``；
    超时抛 ``TimeoutError``。``__exit__`` 仅在成功获取后释放，避免泄漏。
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
    """沙盒执行器抽象基类。"""

    @abstractmethod
    async def execute(self, code: str) -> Tuple[bool, str, Dict[str, Any]]:
        """执行代码，返回 ``(success, output, metadata)``。

        - ``success=True``  → ``output`` 为 stdout 内容
        - ``success=False`` → ``output`` 为错误信息
        - ``metadata``      → dict，含 ``executor`` / ``exit_code`` /
          ``execution_time_ms`` / ``stdout_lines`` / ``stderr`` 等
        """
        ...


class DifySandboxExecutor(BaseSandboxExecutor):
    """Dify 沙盒服务执行器（HTTP）。

    通过 HTTP POST 调用远端沙盒服务执行代码，服务侧负责隔离与资源限制::

        POST {api_url}
        headers: {"Content-Type": "application/json", "X-API-Key": <api_key>}
        body:    {"language": "python3", "code": <code>, "stdin": ""}
        resp:    {"code": 0, "data": {"stdout": "...", "stderr"/"error": "..."}}

    环境变量：
      ``SANDBOX_API_URL``  = http://sandbox.dify01:8194/v1/sandbox/run（默认）
      ``SANDBOX_API_KEY``  = dify-sandbox（默认）
      ``SANDBOX_LANGUAGE`` = python3（默认）
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
        # 提交前本地拦截（长度 / 绘图库）
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

        # 进程级并发 lane：超出并发抛 TimeoutError → 归一化为连接级失败
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
        # 服务侧 code != 0 → 服务/请求级失败（exit_code=-2），错误详情多在 result["message"]。
        service_ok = result.get("code", 0) in (0, None)
        service_msg = "" if service_ok else str(result.get("message") or "").strip()
        # stderr 可能只是 warning；仅当含真正异常/语法错误才判失败。
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
