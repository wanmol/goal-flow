"""``EntryGuardMiddleware`` top-level public entry point.

The actual implementation still lives in ``agent_kit.harness.middleware.entry_guard``; this module only
re-exports it, so that ``from agent_kit.middleware import EntryGuardMiddleware`` also works for the business.
"""
from agent_kit.harness.middleware.entry_guard import (
    EntryGuardMiddleware,
    GuardPredicate,
    GuardResult,
)

__all__ = ["EntryGuardMiddleware", "GuardPredicate", "GuardResult"]
