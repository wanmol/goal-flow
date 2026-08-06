"""``node/_harness_bootstrap``：共享的 agent_kit Harness 接线代码。

把 ``node/agent_node_mixin.py`` 里原本内联的 ``_streaming_llm_factory`` 与
``_ensure_harness_wired()`` 抽到独立模块，让：

- 老 ``node/agent_node_mixin.py``（P5 标记废弃，但仍工作）
- 新 ``node/agent_base.py`` (基于 ADR-003 的 ``Agent`` 类的 workflow 适配)

都能 import 同一份接线代码，不互相依赖、不重复定义。

``_ensure_harness_wired`` 是幂等的——多次调用安全。约定：每个新 workflow base 在
模块顶部调用一次，或在子类 ``__init__`` 里调用一次（``Harness`` 内部 ``HARNESS_*``
单例共享，所以重复 wire 不会污染状态）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 未 pip install 时（如 python start_server.py），保证 src/ 在 sys.path 上，
# 使 goalflow 与 vendored agent_kit 均可 import。
# 布局: src/goalflow/node/_harness_bootstrap.py → parents[3] == 项目根目录。
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bootstrap_paths import ensure_project_paths

ensure_project_paths()

from agent_kit.harness import HARNESS_OBS, HARNESS_ROUTER

from goalflow.tool.metrics import emit_counter, emit_histogram


def _streaming_llm_factory(**kwargs):
    """Agent 用 LLM 默认开启 streaming，供 graph.stream(messages) 逐 token 输出。

    本仓库的 ``LLM.create()`` 是 kwarg-only 签名，只认 provider/model/temperature/max_tokens；
    HARNESS_ROUTER 兼容层传来的 ``timeout`` / ``max_retries`` / ``streaming`` 等扩展 kwarg
    需要在这里过滤掉，避免 ``TypeError: got an unexpected keyword argument``。
    """
    from goalflow.llm import LLM

    _ALLOWED = ("provider", "model", "temperature", "max_tokens")
    filtered = {k: v for k, v in kwargs.items() if k in _ALLOWED}
    model = LLM.create(**filtered)
    if hasattr(model, "streaming"):
        model.streaming = True
    return model


def ensure_harness_wired() -> None:
    """应用启动一次：把本仓库的 LLM 工厂、metric、Langfuse 接到 agent_kit Harness。

    幂等：多次调用安全（factory 已注册则跳过；emitter 重复 set 也无副作用）。

    重要：本函数操作的是 ``HARNESS_ROUTER`` / ``HARNESS_OBS`` 全局单例对象。按 ADR-003
    的不变量，``default_harness()`` 返回的 ``Harness`` 实例的 ``router`` / ``tracer``
    属性 *就是* 同一组对象——所以本函数对新 ``Agent`` API 与老 ``AgentRuntime`` API 同时生效。
    """
    if HARNESS_ROUTER._factory is None:  # noqa: SLF001
        HARNESS_ROUTER.register_llm_factory(_streaming_llm_factory)

    HARNESS_OBS.set_counter_emitter(emit_counter)
    HARNESS_OBS.set_histogram_emitter(emit_histogram)
    HARNESS_OBS.enable_langfuse()


# 模块 import 时自动跑一次，与老 agent_node_mixin.py 行为一致
ensure_harness_wired()
