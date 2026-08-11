"""Harness: an instantiation container for governance infrastructure.

Design intent: replace the five process-level ``HARNESS_*`` global singletons, letting an Agent
explicitly inject governance dependencies via ``Agent(harness=...)``. This makes it easy to:

- Isolate unit tests (constructing a fresh ``Harness()`` won't pollute other tests)
- Coexist multiple configurations (run two sets of LLM routing in the same process)
- Make dependencies explicit (the signature tells you which governance capabilities the Agent uses)

Legacy API compatibility: the attributes of the ``Harness`` instance returned by ``default_harness()``
**are** the legacy ``HARNESS_*`` singleton objects themselves (not copied, shared state). So what
business code registers via the legacy API ``HARNESS_ROUTER.configure(...)`` is also visible through
``default_harness().router.get(...)`` -- and vice versa.
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
    """Governance instance container.

    No arguments at construction → all 5 components are independent new instances, fully isolated
    from the global ``HARNESS_*`` singletons (suitable for unit tests).

    Arguments passed at construction (e.g. ``Harness(router=HARNESS_ROUTER, ...)``) → shares the
    state of the passed-in instances. ``default_harness()`` takes this path.
    """

    settings: HarnessSettings = field(default_factory=HarnessSettings)
    router: ModelRouter = field(default_factory=ModelRouter)
    prompts: PromptRegistry = field(default_factory=PromptRegistry)
    tracer: Observability = field(default_factory=Observability)
    profiles: ProfileRegistry = field(default_factory=ProfileRegistry)


_DEFAULT_HARNESS: Optional[Harness] = None


def default_harness() -> Harness:
    """Return the process-level default ``Harness``.

    This instance's 5 attributes **are** the legacy ``HARNESS_*`` singleton objects themselves
    (sharing the same state). So the new and old API paths read and write the same governance state.

    Recommended business usage:

        from agent_kit import default_harness, Agent

        class MyAgent(Agent):
            name = "category_classify"
            def __init__(self):
                super().__init__(harness=default_harness(), ...)

    Unit-test isolation usage:

        harness = Harness()  # fresh ModelRouter / PromptRegistry / ...
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
    """Unit-test only: reset ``_DEFAULT_HARNESS`` so the next call to ``default_harness()``
    re-binds to the possibly-replaced ``HARNESS_*`` singletons."""
    global _DEFAULT_HARNESS
    _DEFAULT_HARNESS = None
