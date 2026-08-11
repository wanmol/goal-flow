"""``node/_harness_bootstrap``: shared agent_kit Harness wiring code.

Extracts the ``_streaming_llm_factory`` and ``_ensure_harness_wired()`` that were
originally inlined in ``node/agent_node_mixin.py`` into a standalone module, so that:

- the old ``node/agent_node_mixin.py`` (marked deprecated in P5, but still working)
- the new ``node/agent_base.py`` (workflow adaptation of the ADR-003-based ``Agent`` class)

can both import the same wiring code, without depending on each other or duplicating definitions.

``_ensure_harness_wired`` is idempotent -- safe to call multiple times. Convention: each new
workflow base calls it once at the top of the module, or once in the subclass ``__init__``
(the ``Harness`` internal ``HARNESS_*`` singletons are shared, so re-wiring does not pollute state).
"""
from __future__ import annotations

import sys
from pathlib import Path

# When not pip installed (e.g. python start_server.py), ensure src/ is on sys.path
# so that both goalflow and the vendored agent_kit can be imported.
# Layout: src/goalflow/node/_harness_bootstrap.py → parents[3] == project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bootstrap_paths import ensure_project_paths

ensure_project_paths()

from agent_kit.harness import HARNESS_OBS, HARNESS_ROUTER

from goalflow.tool.metrics import emit_counter, emit_histogram


def _streaming_llm_factory(**kwargs):
    """The Agent LLM enables streaming by default, so graph.stream(messages) emits token by token.

    This repo's ``LLM.create()`` has a kwarg-only signature and only accepts provider/model/temperature/max_tokens;
    the extended kwargs passed by the HARNESS_ROUTER compatibility layer, such as ``timeout`` / ``max_retries`` / ``streaming``,
    must be filtered out here to avoid ``TypeError: got an unexpected keyword argument``.
    """
    from goalflow.llm import LLM

    _ALLOWED = ("provider", "model", "temperature", "max_tokens")
    filtered = {k: v for k, v in kwargs.items() if k in _ALLOWED}
    model = LLM.create(**filtered)
    if hasattr(model, "streaming"):
        model.streaming = True
    return model


def ensure_harness_wired() -> None:
    """Run once at app startup: wire this repo's LLM factory, metrics, and Langfuse into the agent_kit Harness.

    Idempotent: safe to call multiple times (skips if the factory is already registered; re-setting emitters has no side effect).

    Important: this function operates on the ``HARNESS_ROUTER`` / ``HARNESS_OBS`` global singleton objects. Per the ADR-003
    invariant, the ``router`` / ``tracer`` attributes of the ``Harness`` instance returned by ``default_harness()``
    *are* the same set of objects -- so this function takes effect for both the new ``Agent`` API and the old ``AgentRuntime`` API.
    """
    if HARNESS_ROUTER._factory is None:  # noqa: SLF001
        HARNESS_ROUTER.register_llm_factory(_streaming_llm_factory)

    HARNESS_OBS.set_counter_emitter(emit_counter)
    HARNESS_OBS.set_histogram_emitter(emit_histogram)
    HARNESS_OBS.enable_langfuse()


# Runs once automatically on module import, consistent with the old agent_node_mixin.py behavior
ensure_harness_wired()
