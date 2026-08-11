"""
Trace-related functionality module

The trace mechanism uniformly uses langfuse (integrated via the CallbackHandler in base_workflow).
"""
from goalflow.trace.langfuse import TruncatedCallbackHandler

__all__ = [
    'TruncatedCallbackHandler',
]
