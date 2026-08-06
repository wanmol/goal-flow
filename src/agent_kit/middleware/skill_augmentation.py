"""SkillAugmentationMiddleware：把 skill 详情拼进 system prompt + 路由 skill tool。

设计意图：替代 ``AgentRuntime`` 在 ``run()`` 状态机里调用 ``SkillOrchestrator``
的 ad-hoc 集成。本中间件做两件事：

1. ``@dynamic_prompt`` 维度：每轮匹配最相关的 skill 详情拼进 system prompt
2. ``wrap_tool_call`` 维度：跟踪 skill tool 调用做 metric / 标签（可选）

业务用法::

    from agent_kit import SkillOrchestrator, SkillAugmentationMiddleware

    orch = SkillOrchestrator.create_default("./skills")
    agent = Agent(
        middleware=[SkillAugmentationMiddleware(orch, match_top_k=3, match_threshold=0.3)],
        tools=orch.materialize_tools(...),  # 把 executable skill 转 LangChain tool
        ...
    )

匹配出错时**静默回退原 prompt**（不让 skill 失败拖垮主流程）——与
``AgentRuntime.run()`` 的现有 fallback 行为一致。
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
from langchain_core.messages import SystemMessage
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

logger = logging.getLogger(__name__)


def _extract_query(request: ModelRequest) -> str:
    """从 request 拿最近一条 user 消息内容做 skill 匹配 query。"""
    from langchain_core.messages import HumanMessage

    messages = request.messages or []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        return str(block["text"])
                    if isinstance(block, str):
                        return block
            return str(content) if content else ""
    return ""


def _existing_system_prompt(request: ModelRequest) -> str:
    sm = request.system_message
    if sm is None:
        return ""
    if isinstance(sm, SystemMessage):
        content = sm.content
        return content if isinstance(content, str) else str(content)
    return str(sm)


class SkillAugmentationMiddleware(
    AgentMiddleware[ContextAgentState, ContextT, ResponseT]
):
    """在每轮 model 调用前，把匹配出的 skill 详情拼进 system prompt。

    构造参数：
    - ``orchestrator``：``SkillOrchestrator`` 实例
    - ``match_top_k``：每轮最多匹配的 skill 数（默认 3）
    - ``match_threshold``：匹配置信度阈值（默认 0.3）
    - ``query_extractor``：自定义 query 抽取（默认从 messages 末尾的 HumanMessage 拿）
    """

    def __init__(
        self,
        orchestrator: Any,
        *,
        match_top_k: int = 3,
        match_threshold: float = 0.3,
        query_extractor: Optional[Callable[[ModelRequest], str]] = None,
    ):
        self._orchestrator = orchestrator
        self._top_k = match_top_k
        self._threshold = match_threshold
        self._query_extractor = query_extractor or _extract_query

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        try:
            query = self._query_extractor(request)
            if not query:
                return handler(request)
            base_prompt = _existing_system_prompt(request)
            augmented = self._orchestrator.match_and_augment(
                query=query,
                base_prompt=base_prompt,
                top_k=self._top_k,
                threshold=self._threshold,
            )
            if augmented and augmented != base_prompt:
                request = request.override(system_message=SystemMessage(content=augmented))
        except Exception as e:
            logger.warning(
                f"SkillAugmentationMiddleware: augmentation failed, "
                f"continuing with base prompt: {e}"
            )
        return handler(request)
