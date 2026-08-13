"""Pluggable knowledge retrieval layer.

Public API:
    KnowledgeRetriever      abstract backend contract
    RetrievedChunk          one retrieved result
    RetrievalConfig         normalized retrieval parameters
    KnowledgeRetrievalError raised on backend/config failure
    get_retriever()         process-wide retriever (env-configured)
    set_retriever(r)        inject a custom backend
"""

from goalflow.knowledge.base import (
    KnowledgeRetriever,
    KnowledgeRetrievalError,
    RetrievalConfig,
    RetrievedChunk,
    UnconfiguredRetriever,
)
from goalflow.knowledge.embedding import (
    TextEmbedder,
    EmbeddingError,
    get_embedder,
)
from goalflow.knowledge.factory import get_retriever, set_retriever

__all__ = [
    "KnowledgeRetriever",
    "KnowledgeRetrievalError",
    "RetrievalConfig",
    "RetrievedChunk",
    "UnconfiguredRetriever",
    "TextEmbedder",
    "EmbeddingError",
    "get_embedder",
    "get_retriever",
    "set_retriever",
    "chunk_text",
    "MilvusIngestor",
    "IngestConfig",
]


def __getattr__(name):
    # Lazily expose ingestion symbols so importing the package doesn't pull in
    # ingest-only deps unless the ingestion tool is actually used.
    if name in ("chunk_text", "MilvusIngestor", "IngestConfig", "IngestResult"):
        from goalflow.knowledge import ingest

        return getattr(ingest, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
