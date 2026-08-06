"""Harness：治理基础设施的实例化容器。

设计意图：替代 ``HARNESS_*`` 五个进程级全局单例，让 Agent 通过 ``Agent(harness=...)``
显式注入治理依赖。便于：

- 单测隔离（构造一个全新 ``Harness()`` 不污染其它测试）
- 多套配置并存（同一进程跑两套 LLM 路由）
- 依赖关系显式化（看签名就知道 Agent 用了哪些治理能力）

兼容旧 API：``default_harness()`` 返回的 ``Harness`` 实例的属性**就是**旧
``HARNESS_*`` 单例对象本身（不复制，共享状态）。所以业务通过老 API
``HARNESS_ROUTER.configure(...)`` 注册的，从 ``default_harness().router.get(...)``
也能拿到——反之亦然。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agent_kit.harness.model_router import ModelRouter
from agent_kit.harness.observability import Observability
from agent_kit.harness.profiles import ProfileRegistry
from agent_kit.harness.prompt_registry import PromptRegistry
from agent_kit.harness.settings import HarnessSettings


@dataclass
class Harness:
    """治理实例容器。

    构造时不传任何参数 → 5 个 component 都是独立新实例，与全局 ``HARNESS_*``
    单例完全隔离（适合单测）。

    构造时传入参数（如 ``Harness(router=HARNESS_ROUTER, ...)``）→ 共享传入实例
    的状态。``default_harness()`` 走这条路。
    """

    settings: HarnessSettings = field(default_factory=HarnessSettings)
    router: ModelRouter = field(default_factory=ModelRouter)
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    tracer: Observability = field(default_factory=Observability)
    profiles: ProfileRegistry = field(default_factory=ProfileRegistry)


_DEFAULT_HARNESS: Optional[Harness] = None


def default_harness() -> Harness:
    """返回进程级默认 ``Harness``。

    该实例的 5 个属性**就是**老 ``HARNESS_*`` 单例对象本身（共享同一份状态）。
    所以新老两条 API 路径对同一份治理状态读写。

    业务推荐用法：

        from agent_kit import default_harness, Agent

        class MyAgent(Agent):
            name = "category_classify"
            def __init__(self):
                super().__init__(harness=default_harness(), ...)

    单测隔离用法：

        harness = Harness()  # 全新 ModelRouter / PromptRegistry / ...
    """
    global _DEFAULT_HARNESS
    if _DEFAULT_HARNESS is None:
        from agent_kit.harness.model_router import HARNESS_ROUTER
        from agent_kit.harness.observability import HARNESS_OBS
        from agent_kit.harness.profiles import HARNESS_PROFILES
        from agent_kit.harness.prompt_registry import HARNESS_PROMPTS
        from agent_kit.harness.settings import HARNESS_SETTINGS

        _DEFAULT_HARNESS = Harness(
            settings=HARNESS_SETTINGS,
            router=HARNESS_ROUTER,
            prompts=HARNESS_PROMPTS,
            tracer=HARNESS_OBS,
            profiles=HARNESS_PROFILES,
        )
    return _DEFAULT_HARNESS


def _reset_default_harness_for_tests() -> None:
    """单测专用：重置 ``_DEFAULT_HARNESS`` 以便下次调用 ``default_harness()``
    重新绑定可能被替换过的 ``HARNESS_*`` 单例。"""
    global _DEFAULT_HARNESS
    _DEFAULT_HARNESS = None
