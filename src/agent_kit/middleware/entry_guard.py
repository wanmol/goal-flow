"""``EntryGuardMiddleware`` 顶层公开入口。

实际实现仍在 ``agent_kit.harness.middleware.entry_guard``；本模块只做 re-export，
让业务 ``from agent_kit.middleware import EntryGuardMiddleware`` 也能工作。
"""
from agent_kit.harness.middleware.entry_guard import (
    EntryGuardMiddleware,
    GuardPredicate,
    GuardResult,
)

__all__ = ["EntryGuardMiddleware", "GuardPredicate", "GuardResult"]
