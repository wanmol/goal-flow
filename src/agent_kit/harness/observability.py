"""
Observability: the unified metric / trace abstraction entry point within agent_kit.

Design principles:
- The agent_kit package does not directly bind to Langfuse / Prometheus / any concrete trace/metric backend
- Abstract interfaces let the caller inject the implementation (the business side wires in emit_counter / Langfuse)
- When unavailable, **everything degrades to noop**, so the business never fails because instrumentation failed
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Callable, Optional

from agent_kit.harness.settings import HARNESS_SETTINGS

logger = logging.getLogger(__name__)

CounterEmitter = Callable[..., None]
HistogramEmitter = Callable[..., None]


def _noop(*args, **kwargs) -> None:  # pragma: no cover
    return None


class SpanContext:
    """The context object returned by ``HARNESS_OBS.span(...)``."""

    def __init__(self, *, span_name: str, session_id: str, callbacks: list) -> None:
        self.span_name = span_name
        self.session_id = session_id
        self.callbacks = callbacks


class Observability:
    """The metric / trace entry point shared across Runtimes.

    Global singleton ``HARNESS_OBS``.
    """

    def __init__(self) -> None:
        self._counter: CounterEmitter = _noop
        self._histogram: HistogramEmitter = _noop
        self._langfuse_enabled: bool = False
        self._langfuse_client = None

    def set_counter_emitter(self, emitter: CounterEmitter) -> None:
        """Inject the counter implementation (the business side's emit_counter)."""
        self._counter = emitter
        logger.info(f"Observability: counter emitter registered ({emitter!r})")

    def set_histogram_emitter(self, emitter: HistogramEmitter) -> None:
        """Inject the histogram implementation (the business side's emit_histogram)."""
        self._histogram = emitter
        logger.info(f"Observability: histogram emitter registered ({emitter!r})")

    def enable_langfuse(self, force: bool = False) -> bool:
        """Enable Langfuse trace. Auto-detects whether langfuse can be imported and whether a client can be built."""
        if not force and not HARNESS_SETTINGS.observability.langfuse_enabled:
            logger.info("Observability: Langfuse disabled by HARNESS_SETTINGS")
            self._langfuse_enabled = False
            return False
        try:
            from langfuse import get_client

            self._langfuse_client = get_client()
            self._langfuse_enabled = True
            logger.info("Observability: Langfuse enabled")
            return True
        except Exception as e:
            logger.warning(f"Observability: Langfuse disabled (setup failed: {e})")
            self._langfuse_enabled = False
            return False

    def disable_langfuse(self) -> None:
        self._langfuse_enabled = False
        self._langfuse_client = None

    def counter(self, metric_name: str, **labels) -> None:
        """Emit a counter. Noop when no emitter is injected; emitter exceptions are swallowed."""
        try:
            self._counter(metric_name, **labels)
        except Exception as e:
            logger.warning(f"Observability.counter({metric_name!r}) failed: {e}")

    def histogram(self, metric_name: str, value: float, **labels) -> None:
        """Emit a histogram. Noop when no emitter is injected; emitter exceptions are swallowed."""
        try:
            self._histogram(metric_name, value=value, **labels)
        except Exception as e:
            logger.warning(f"Observability.histogram({metric_name!r}) failed: {e}")

    @contextmanager
    def span(self, span_name: str, *, session_id: str, metadata: Optional[dict] = None):
        """trace span context manager.

        metadata: injected via langfuse propagate_attributes, automatically applied to all child
        observations (including the TOOL / GENERATION created by the LangChain CallbackHandler),
        making it convenient to filter in the UI by business dimension.
        """
        callbacks: list = []
        propagate_cm = None
        observation_cm = None

        if self._langfuse_enabled and self._langfuse_client is not None:
            try:
                from langfuse import propagate_attributes
                from langfuse.langchain import CallbackHandler

                propagate_kwargs: dict = {"session_id": session_id}
                if metadata:
                    propagate_kwargs["metadata"] = metadata
                propagate_cm = propagate_attributes(**propagate_kwargs)
                observation_cm = self._langfuse_client.start_as_current_observation(
                    as_type="span", name=span_name
                )
                callbacks.append(CallbackHandler())
            except Exception as e:
                logger.warning(
                    f"Observability.span({span_name!r}): Langfuse setup failed: {e}"
                )
                propagate_cm = None
                observation_cm = None

        ctx = SpanContext(span_name=span_name, session_id=session_id, callbacks=callbacks)

        if propagate_cm is not None and observation_cm is not None:
            with propagate_cm:
                with observation_cm:
                    yield ctx
        else:
            yield ctx

    def reset(self) -> None:
        """Restore everything to the noop state. For unit tests only."""
        self._counter = _noop
        self._histogram = _noop
        self._langfuse_enabled = False
        self._langfuse_client = None


HARNESS_OBS = Observability()
