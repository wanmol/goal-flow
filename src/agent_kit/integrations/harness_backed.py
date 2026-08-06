"""
HarnessBacked mixin：让任意 AgentRuntime 子类自动接 Harness 的 Model Router + Profiles.

用法::

    class MyAgent(HarnessBacked, DeepAgentRuntime[MyResult]):
        task_type = "requirement_collection"

    HARNESS_PROFILES.register(
        "requirement_collection",
        llm={"temperature": 0.1},
        skills_dir="./skills/req",
    )
    # 或老 API：
    HARNESS_ROUTER.register_llm_factory(LLM.create)
    HARNESS_ROUTER.configure("requirement_collection", temperature=0.1)
"""
from __future__ import annotations

from typing import Any, Optional


class HarnessBacked:
    """让 AgentRuntime 子类自动从 ``HARNESS_ROUTER`` 拿 LLM + 自动读 ``HARNESS_PROFILES``
    里的 skill 配置。

    必须设置类属性 ``task_type``。

    Profile 自动接入（P9-a）：
        - 业务通过 ``HARNESS_PROFILES.register(task_type, skills_dir=..., ...)`` 注册后，
          本 mixin 的 ``skills_dir()`` / ``skill_match_top_k()`` / ``skill_match_threshold()``
          会自动从 profile 读取
        - 业务子类 override 这些钩子时，优先级**高于** profile（Python MRO 自然实现）
        - 没注册 profile 时，行为与基类默认一致（skills_dir() 返回 None，跳过 skill）
    """

    task_type: str = ""

    def _get_llm(self):
        if getattr(self, "_llm", None) is not None:
            return self._llm

        if not self.task_type:
            raise RuntimeError(
                f"{type(self).__name__}: task_type is empty; "
                "HarnessBacked subclasses must set `task_type` class attribute "
                "to enable automatic LLM routing."
            )

        from agent_kit.harness.model_router import HARNESS_ROUTER

        llm = HARNESS_ROUTER.get(self.task_type)
        self._llm = llm
        return llm

    @property
    def profile(self):
        """读本 task_type 对应的 ``HarnessProfile``；未注册返回 None。"""
        if not self.task_type:
            return None
        from agent_kit.harness.profiles import HARNESS_PROFILES

        return HARNESS_PROFILES.get(self.task_type)

    # ───── Skill 配置默认值：从 profile 读，子类 override 优先级更高 ────

    def skills_dir(self) -> Optional[str]:
        """skills 根目录。默认从 ``HARNESS_PROFILES`` 读；未注册或 profile 没设则 None。"""
        p = self.profile
        return p.skills_dir if p else None

    def skill_match_top_k(self) -> int:
        p = self.profile
        return p.skill_match_top_k if p else 3

    def skill_match_threshold(self) -> float:
        p = self.profile
        return p.skill_match_threshold if p else 0.3
