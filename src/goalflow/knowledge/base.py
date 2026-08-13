"""Knowledge retrieval abstraction.

Defines the pluggable contract a knowledge backend must satisfy so that
``KnowledgeRetrievalNode`` stays backend-agnostic. Concrete backends (HTTP
service, vector store, Dify dataset API, ...) implement ``KnowledgeRetriever``
and are selected at runtime by :func:`goalflow.knowledge.factory.get_retriever`.

Design goals:
- The node never talks to a concrete backend directly.
- A missing/unconfigured backend fails loudly (raises) rather than silently
  returning empty results, which previously looked like a successful retrieval.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


class KnowledgeRetrievalError(Exception):
    """Raised when retrieval fails (backend error, misconfiguration, timeout)."""


@dataclass
class RetrievedChunk:
    """A single retrieved knowledge chunk.

    The fields mirror what downstream nodes expect from a Dify knowledge node
    (``content``/``title``/``url``), plus a relevance ``score`` and free-form
    ``metadata`` for backend-specific extras (dataset id, document id, ...).
    """

    content: str
    title: str = ""
    url: str = ""
    score: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_output(self) -> dict[str, Any]:
        """Shape used when writing results into workflow state."""
        return {
            "content": self.content,
            "title": self.title,
            "url": self.url,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class RetrievalConfig:
    """Normalized retrieval parameters, decoupled from the Dify DSL shape.

    The node builds this from its parsed configuration and hands it to the
    retriever, so backends receive one stable structure regardless of the
    source visual tool.
    """

    dataset_ids: Sequence[str] = field(default_factory=list)
    retrieval_mode: str = "multiple"          # "single" | "multiple"
    top_k: int = 5
    score_threshold: Optional[float] = None
    reranking_enable: bool = False
    reranking_model: Optional[dict[str, Any]] = None
    metadata_filtering: Optional[dict[str, Any]] = None

    @classmethod
    def from_node_config(cls, raw: Optional[dict[str, Any]]) -> "RetrievalConfig":
        """Build from the dict the node carries (parser output).

        Tolerant of missing keys so partially-specified DSL exports still work;
        unknown extras are ignored rather than raising.
        """
        raw = raw or {}
        multiple = raw.get("multiple_retrieval_config") or {}
        return cls(
            dataset_ids=list(raw.get("dataset_ids") or []),
            retrieval_mode=raw.get("retrieval_mode") or "multiple",
            top_k=int(multiple.get("top_k", raw.get("top_k", 5)) or 5),
            score_threshold=multiple.get("score_threshold", raw.get("score_threshold")),
            reranking_enable=bool(multiple.get("reranking_enable", False)),
            reranking_model=multiple.get("reranking_model"),
            metadata_filtering=raw.get("metadata_filtering_conditions"),
        )


class KnowledgeRetriever(ABC):
    """Pluggable knowledge retrieval backend.

    Implementations must be safe to construct once and reuse across requests
    (the factory caches a singleton). ``retrieve`` should raise
    :class:`KnowledgeRetrievalError` on failure rather than return empty.
    """

    @abstractmethod
    def retrieve(self, query: str, config: RetrievalConfig) -> list[RetrievedChunk]:
        """Return chunks relevant to ``query`` under ``config``.

        Args:
            query: the user/query text to search for.
            config: normalized retrieval parameters (datasets, top_k, ...).

        Raises:
            KnowledgeRetrievalError: on backend error or misconfiguration.
        """
        raise NotImplementedError


class UnconfiguredRetriever(KnowledgeRetriever):
    """Default backend used when no retriever is configured.

    Deliberately fails loudly so an unimplemented/unconfigured knowledge node
    surfaces as an error (and can be routed via the node's error strategy)
    instead of silently yielding an empty result that downstream nodes mistake
    for a successful-but-empty retrieval.
    """

    def __init__(self, reason: str = "no knowledge retriever configured"):
        self._reason = reason

    def retrieve(self, query: str, config: RetrievalConfig) -> list[RetrievedChunk]:
        raise KnowledgeRetrievalError(
            f"Knowledge retrieval is not available: {self._reason}. "
            "Set KNOWLEDGE_RETRIEVER_BACKEND and its endpoint/key, or register a "
            "custom retriever via goalflow.knowledge.factory.set_retriever()."
        )
