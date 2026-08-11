"""``ModelFailoverMiddleware`` top-level public entry point."""
from agent_kit.harness.middleware.model_failover import (
    FailoverPredicate,
    ModelFailoverMiddleware,
    default_should_failover,
)

__all__ = [
    "ModelFailoverMiddleware",
    "FailoverPredicate",
    "default_should_failover",
]
