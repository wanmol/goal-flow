"""
Custom langfuse CallbackHandler with string truncation to prevent OOM.
Optional span-event diagnostic logging via LANGFUSE_SPAN_PROBE=1.
"""
import os
import time
from typing import Any, Optional
from uuid import UUID

from langfuse.langchain import CallbackHandler
from goalflow.config import get_logger

logger = get_logger(__name__)

# Known LangChain message types that can be safely processed
KNOWN_MESSAGE_TYPES = {"SystemMessage", "HumanMessage", "AIMessage", "ToolMessage", "FunctionMessage"}

# Truncation limit for langfuse callback to prevent OOM
LANGFUSE_MAX_STRING_LENGTH = int(os.getenv("LANGFUSE_MAX_STRING_LENGTH", "2048"))

# Span-event diagnostic probe: set LANGFUSE_SPAN_PROBE=1 to log span events
LANGFUSE_SPAN_PROBE = True

# Filter out LangGraph internal chain spans (channel read/write / state merge / route)
# Set LANGFUSE_FILTER_INTERNAL_CHAINS=0 to disable this filter.
LANGFUSE_FILTER_INTERNAL_CHAINS = True


def _truncate_string(value: Any, max_length: int = LANGFUSE_MAX_STRING_LENGTH) -> Any:
    """Recursively truncate strings in a data structure to prevent OOM."""
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length] + f"... [truncated {len(value) - max_length} chars]"
        return value
    if isinstance(value, dict):
        return {k: _truncate_string(v, max_length) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_truncate_string(item, max_length) for item in value)
    if isinstance(value, set):
        return {_truncate_string(item, max_length) for item in value}
    return value


def _truncate_prompts(
        prompts: Any,
        max_string_length: int = LANGFUSE_MAX_STRING_LENGTH,
    ) -> Any:
    """
    Truncate prompt messages to prevent large memory usage.
    Handles both LLM (list of strings) and ChatModel (list of list of messages) formats.
    For ChatModel format, creates new message instances with truncated content.
    """
    if prompts is None:
        return None

    # Handle list of strings (LLM format)
    if isinstance(prompts, (list, tuple)) and prompts and isinstance(prompts[0], str):
        return _truncate_string(prompts, max_string_length)

    # Handle list of list of BaseMessage (ChatModel format)
    if isinstance(prompts, (list, tuple)) and prompts and hasattr(prompts[0], '__iter__') and not isinstance(prompts[0], str):
        result = []
        for prompt_list in prompts:
            truncated_list = []
            for msg in prompt_list:
                msg_type = type(msg).__name__
                if msg_type not in KNOWN_MESSAGE_TYPES:
                    continue  # Skip unknown types (e.g., <system_prompt>)
                # Truncate content and copy other attributes without deepcopy
                content = msg.content if hasattr(msg, 'content') else None
                if isinstance(content, str):
                    content = _truncate_string(content, max_string_length)
                new_msg = type(msg)(content=content)
                for k, v in msg.__dict__.items():
                    if k != 'content':
                        setattr(new_msg, k, v)
                truncated_list.append(new_msg)
            result.append(truncated_list)
        return result

    # Fallback: use default
    return prompts


class TruncatedCallbackHandler(CallbackHandler):
    """
    Custom langfuse CallbackHandler that truncates large strings
    to prevent OOM issues during tracing.

    Span-event probe: set env LANGFUSE_SPAN_PROBE=1 to log one line per
    span event (on_chain_start / on_chat_model_start / on_llm_start /
    *_end / on_tool_start / on_retriever_start) before delegating to
    the parent handler.
    """

    # Class-level switch: frozen at import time, branch-free fast path
    _PROBE_ENABLED: bool = LANGFUSE_SPAN_PROBE
    _PROBE_T0: float = time.time() if LANGFUSE_SPAN_PROBE else 0.0

    # Feature keywords for LangGraph 0.2+ internal chains (used to no-op early in on_chain_start,
    # to avoid Langfuse creating spans for these 1-2ms channel read/write / state merge / route nodes)
    # Note: must match exact class names, not broad prefixes like "Pregel"/"langgraph"
    # (PregelNode wraps a business node, and its id path also contains "Pregel"; broad matching would misclassify business nodes)
    _INTERNAL_GRAPH_KEYWORDS: tuple = (
        # Channel read/write/invoke (the state dict is passed back and forth, input/output are the same)
        "ChannelRead", "ChannelWrite", "ChannelInvoke", "ChannelBatch",
        # The Pregel framework itself (not the PregelNode that wraps a business node)
        "PregelLoop", "PregelRunner", "PregelTaskWrites", "PregelTick",
        # Branch conditional branches
        "Branch", "ConditionalBranch",
        # LangGraph 0.2+'s own RunnableSeq (different from LangChain's RunnableSequence)
        "RunnableSeq",
        # Passthrough
        "Passthrough",
        # LangGraph internal small function names
        "_read", "_write", "_invoke",
    )

    @classmethod
    def _is_internal_graph_chain(cls, serialized: Any) -> bool:
        """Identify channel/route/state chains internal to the LangGraph framework.

        When True is returned, the caller should no-op directly (do not call super(), to avoid Langfuse creating a span).
        """
        if not isinstance(serialized, dict):
            return False
        kws = cls._INTERNAL_GRAPH_KEYWORDS
        # 1) Check the id path (list of str)
        sid = serialized.get("id")
        if isinstance(sid, list):
            for token in sid:
                if isinstance(token, str) and any(k in token for k in kws):
                    return True
        # 2) Check the name field (str)
        name = serialized.get("name")
        if isinstance(name, str) and any(k in name for k in kws):
            return True
        return False

    def __init__(
        self,
        *,
        public_key: Optional[str] = None,
        trace_context: Optional[dict] = None,
        max_string_length: int = LANGFUSE_MAX_STRING_LENGTH,
    ) -> None:
        super().__init__(public_key=public_key, trace_context=trace_context)
        self.max_string_length = max_string_length
        # Cache the trace_id (the parent class stores trace_context as-is on self._trace_context)
        self._trace_id: Optional[str] = (
            trace_context.get("trace_id")
            if isinstance(trace_context, dict) else None
        )

    def _probe(self, event: str, run_id: Optional[UUID] = None, **extra) -> None:
        """Emit a structured span-probe log record. No-op when probe is disabled.

        structlog will render the following fields as separate JSON fields (not mixed into msg):
            msg       = event  (e.g. "on_chain_start")
            t         = seconds relative to t0
            run_id    = first 8 chars of run_id
            trace_id  = first 8 chars of trace_id (a separate field, so the log system can filter by trace_id)
            **extra   = extra fields passed in by the caller (n_msgs / parent / n_prompts / name / tool_node, etc.)
        """
        if not self._PROBE_ENABLED:
            return
        logger.info(
            event,
            t=round(time.time() - self._PROBE_T0, 4),
            run_id=str(run_id) if run_id is not None else "None",
            trace_id=str(self._trace_id) if self._trace_id else "None",
            **extra,
        )

    def on_llm_start(
        self,
        serialized: dict,
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        """Override to truncate prompt strings before passing to parent."""
        try:
            self._probe("on_llm_start", kwargs.get("run_id"), n_prompts=len(prompts) if prompts else 0)
            truncated_prompts = _truncate_prompts(prompts, max_string_length=self.max_string_length)
            super().on_llm_start(serialized, truncated_prompts, **kwargs)
        except Exception as e:
            logger.error(
                f"Langfuse callback on_llm_start error, trace skipped: {e}",
                exc_info=True,
            )

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        """Override to truncate chat messages before passing to parent."""
        try:
            self._probe("on_chat_model_start", kwargs.get("run_id"), n_msgs=len(messages) if messages else 0)
            truncated_messages = _truncate_prompts(messages, max_string_length=self.max_string_length)
            super().on_chat_model_start(serialized, truncated_messages, **kwargs)
        except Exception as e:
            logger.error(
                f"Langfuse callback on_chat_model_start error, trace skipped: {e}",
                exc_info=True,
            )

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Override to truncate LLM response output before passing to parent."""
        try:
            self._probe("on_llm_end", kwargs.get("run_id"))
            truncated_response = _truncate_string(response, self.max_string_length)
            super().on_llm_end(truncated_response, **kwargs)
        except Exception as e:
            logger.error(
                f"Langfuse callback on_llm_end error, trace skipped: {e}",
                exc_info=True,
            )

    def on_chain_start(
        self,
        serialized: Optional[dict],
        inputs: Any,
        **kwargs: Any,
    ) -> None:
        # 1) Filter out LangGraph internal channel/route/state chains
        if LANGFUSE_FILTER_INTERNAL_CHAINS and self._is_internal_graph_chain(serialized):
            return

        run_id = kwargs.get("run_id")
        parent_run_id = kwargs.get("parent_run_id")

        # Business chain -> pass through normally
        self._probe(
            "on_chain_start", run_id,
            parent=str(parent_run_id) if parent_run_id else "None",
            name=kwargs.get("name") or "-",
        )
        try:
            super().on_chain_start(serialized, inputs, **kwargs)
        except Exception as e:
            logger.error(f"on_chain_start error: {e}", exc_info=True)

    def on_chain_end(self, outputs: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        # Normal business chain end
        self._probe("on_chain_end", run_id)
        try:
            super().on_chain_end(outputs, **kwargs)
        except Exception as e:
            logger.error(f"on_chain_end error: {e}", exc_info=True)

    def on_tool_start(
        self,
        serialized: Optional[dict],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        self._probe(
            "on_tool_start", kwargs.get("run_id"),
            parent=str(kwargs.get("parent_run_id")) if kwargs.get("parent_run_id") else "None",
        )
        try:
            super().on_tool_start(serialized, input_str, **kwargs)
        except Exception as e:
            logger.error(f"on_tool_start error: {e}", exc_info=True)

    def on_retriever_start(
        self,
        serialized: Optional[dict],
        query: str,
        **kwargs: Any,
    ) -> None:
        self._probe(
            "on_retriever_start", kwargs.get("run_id"),
            parent=str(kwargs.get("parent_run_id")) if kwargs.get("parent_run_id") else "None",
        )
        try:
            super().on_retriever_start(serialized, query, **kwargs)
        except Exception as e:
            logger.error(f"on_retriever_start error: {e}", exc_info=True)
