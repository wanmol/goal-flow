"""
Trace 相关功能模块

trace 机制统一使用 langfuse（通过 base_workflow 中的 CallbackHandler 接入）。
"""
from goalflow.trace.langfuse import TruncatedCallbackHandler

__all__ = [
    'TruncatedCallbackHandler',
]
