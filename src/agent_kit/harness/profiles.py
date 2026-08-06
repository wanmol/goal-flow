"""HarnessProfile：task_type 一站式治理配置。

把"配 LLM + 注册 Prompts + 设 skills_dir + 调 skill 匹配阈值"四件事
收敛到一次 register() 调用，避免业务 startup 散落 6+ 次 ``HARNESS_ROUTER.configure`` /
``HARNESS_PROMPTS.register`` 调用。

设计要点：
- **薄包装**：内部调用现有 ``HARNESS_ROUTER.configure`` + ``HARNESS_PROMPTS.register``，
  不引入新存储；旧 API 继续工作。
- **task_type 是一级总线**：profile 决定主 task_type + 子 task_type 命名规范
  （``<task_type>.<sub_name>``）+ prompt 命名规范（``<task_type>.<prompt_name>``）。
- **可选字段**：除 task_type 外都可选；只配关心的字段。

典型用法::

    HARNESS_PROFILES.register(
        "guided_clarification",
        llm={"temperature": 0.0, "model": "qwen-plus"},
        sub_llms={
            "match_fit": {"temperature": 0.1, "streaming": False},
            "extract": {"temperature": 0.0},
        },
        prompts={
            "system_clarify": _fallback_clarify,
            "system_commercial": _fallback_commercial,
        },
        skills_dir="./skills/guided_clarification",
    )

    # Runtime / business 读：
    profile = HARNESS_PROFILES.get("guided_clarification")
    profile.task_type           # "guided_clarification"
    profile.skills_dir          # "./skills/..."
    profile.skill_match_top_k   # 3
    profile.sub_task_type("match_fit")  # "guided_clarification.match_fit"
    profile.prompt_name("system_clarify")  # "guided_clarification.system_clarify"
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class HarnessProfile:
    """单个 task_type 的治理配置快照。"""

    task_type: str
    llm: dict = field(default_factory=dict)
    sub_llms: dict[str, dict] = field(default_factory=dict)
    prompts: dict[str, Callable[..., str]] = field(default_factory=dict)
    skills_dir: Optional[str] = None
    skill_match_top_k: int = 3
    skill_match_threshold: float = 0.3
    extra: dict = field(default_factory=dict)

    def sub_task_type(self, name: str) -> str:
        """子 task_type 命名约定：<task_type>.<name>。"""
        return f"{self.task_type}.{name}"

    def prompt_name(self, name: str) -> str:
        """prompt 命名约定：<task_type>.<name>。"""
        return f"{self.task_type}.{name}"


class ProfileRegistry:
    """全局 ProfileRegistry 单例（``HARNESS_PROFILES``）。"""

    def __init__(self) -> None:
        self._profiles: dict[str, HarnessProfile] = {}
        self._lock = threading.RLock()

    def register(
        self,
        task_type: str,
        *,
        llm: Optional[dict] = None,
        sub_llms: Optional[dict[str, dict]] = None,
        prompts: Optional[dict[str, Callable[..., str]]] = None,
        skills_dir: Optional[str] = None,
        skill_match_top_k: int = 3,
        skill_match_threshold: float = 0.3,
        **extra,
    ) -> HarnessProfile:
        """一次性注册 task_type 的完整治理配置。

        内部 fan-out 到 ``HARNESS_ROUTER.configure`` 和 ``HARNESS_PROMPTS.register``。
        重复注册同名 task_type 会覆盖。

        :param llm: 主 task_type 的 LLM 配置，如 ``{"provider": "qwen", "model": "qwen-plus", "temperature": 0.0}``
        :param sub_llms: 子 task_type 配置；key 是子名（不带 task_type 前缀），值是 LLM 配置 dict
        :param prompts: prompt 名 → fallback callable；prompt 全名会变成 ``<task_type>.<name>``
        :param skills_dir: skill 根目录（业务节点可通过 profile.skills_dir 读）
        :param skill_match_top_k / threshold: skill 匹配参数（业务节点可通过 profile 读）
        :param extra: 业务自定义字段，存到 profile.extra
        """
        from agent_kit.harness.model_router import HARNESS_ROUTER
        from agent_kit.harness.prompt_registry import HARNESS_PROMPTS

        profile = HarnessProfile(
            task_type=task_type,
            llm=dict(llm or {}),
            sub_llms={k: dict(v) for k, v in (sub_llms or {}).items()},
            prompts=dict(prompts or {}),
            skills_dir=skills_dir,
            skill_match_top_k=skill_match_top_k,
            skill_match_threshold=skill_match_threshold,
            extra=dict(extra),
        )

        if profile.llm:
            HARNESS_ROUTER.configure(task_type, **profile.llm)
        for sub_name, sub_cfg in profile.sub_llms.items():
            HARNESS_ROUTER.configure(profile.sub_task_type(sub_name), **sub_cfg)
        for prompt_short_name, fallback_callable in profile.prompts.items():
            HARNESS_PROMPTS.register(
                name=profile.prompt_name(prompt_short_name),
                fallback_callable=fallback_callable,
            )

        with self._lock:
            self._profiles[task_type] = profile
        logger.info(
            f"HARNESS_PROFILES: registered task_type={task_type!r} "
            f"(sub_llms={list(profile.sub_llms.keys())}, "
            f"prompts={list(profile.prompts.keys())}, "
            f"skills_dir={'yes' if skills_dir else 'no'})"
        )
        return profile

    def get(self, task_type: str) -> Optional[HarnessProfile]:
        """读 profile；未注册返回 None。"""
        with self._lock:
            return self._profiles.get(task_type)

    def reset(self) -> None:
        """清空所有 profile 注册。仅单测使用。

        注意：本方法不级联清理 ``HARNESS_ROUTER._configs`` / ``HARNESS_PROMPTS``
        里 ``register()`` 时 fan-out 写入的副作用。测试间想完全隔离须自行：

            HARNESS_PROFILES.reset()
            HARNESS_ROUTER.reset_all()
            HARNESS_PROMPTS.reset()
        """
        with self._lock:
            self._profiles.clear()


HARNESS_PROFILES = ProfileRegistry()
