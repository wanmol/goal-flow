"""StreamingBridgeMiddleware：从 RunnableConfig 把 stream callback 桥接到 token 推送。

设计意图：替代 ``AgentRuntime`` 用 ContextVar 持有 ``stream_callback`` 的老做法。
新做法是 LangChain 标准的"配置随调用走"——业务在 ``Agent.run(state, query, config=...)``
时把 callback 放进 ``RunnableConfig.configurable["stream_callback"]``，中间件读出来。

工作机制：``after_model`` 钩子读出 response 末尾的 AIMessage，按 token 拆分推送。
真正的 token 级流式（每个 chunk 推一次）需要 graph 用 ``.astream(stream_mode='messages')``
驱动；本 middleware 提供配套的 callback 读取与触发逻辑。

业务用法::

    def on_token(text: str) -> None:
        print(text, end="", flush=True)

    agent.run(state, query, config={"configurable": {"stream_callback": on_token}})
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

logger = logging.getLogger(__name__)

StreamCallback = Callable[[str], None]


def _extract_text(content: Any) -> str:
    """归一化 AIMessage.content 为字符串（兼容 list-of-dict 形态）。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "".join(parts)
    return str(content)


class StreamingBridgeMiddleware(
    AgentMiddleware[ContextAgentState, ContextT, ResponseT]
):
    """把 model 输出推到 ``RunnableConfig.configurable["stream_callback"]``。

    构造参数：
    - ``config_key``：从 ``runtime.config["configurable"][config_key]`` 读 callback；
      默认 ``"stream_callback"``
    - ``push_on``：``"after_model"`` 触发时机（默认）。设为 ``"none"`` 可以禁用自动推送
      （仅做 callback 注入到 state，业务自己驱动）
    """

    def __init__(
        self,
        *,
        config_key: str = "stream_callback",
        push_on: str = "after_model",
    ):
        self._config_key = config_key
        self._push_on = push_on

    def _resolve_callback(
        self, runtime: "Runtime[ContextT]"
    ) -> Optional[StreamCallback]:
        cfg = getattr(runtime, "config", None) or {}
        configurable = cfg.get("configurable") if isinstance(cfg, dict) else None
        if not configurable:
            return None
        cb = configurable.get(self._config_key)
        return cb if callable(cb) else None

    @override
    def after_model(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        if self._push_on != "after_model":
            return None
        cb = self._resolve_callback(runtime)
        if cb is None:
            return None
        messages = state.get("messages") or []
        if not messages:
            return None
        last = messages[-1]
        if not isinstance(last, AIMessage):
            return None
        # 跳过纯 tool_call（无文本内容）
        if getattr(last, "tool_calls", None) and not last.content:
            return None
        text = _extract_text(last.content)
        if not text:
            return None
        try:
            cb(text)
        except Exception as e:
            logger.warning(f"StreamingBridgeMiddleware: callback raised: {e}")
        return None
