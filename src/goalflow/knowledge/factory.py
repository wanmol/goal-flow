"""Knowledge retriever factory.

Selects and caches the process-wide :class:`~goalflow.knowledge.base.KnowledgeRetriever`
based on environment configuration, and lets applications inject a custom one.

Environment:
    KNOWLEDGE_RETRIEVER_BACKEND      "http" | "milvus" | "none"  (default: "none")
    KNOWLEDGE_RETRIEVER_ENDPOINT     retrieval service URL (required for "http")
    KNOWLEDGE_RETRIEVER_API_KEY      bearer token (optional)
    KNOWLEDGE_RETRIEVER_TIMEOUT      read timeout seconds (default: 30)
    KNOWLEDGE_RETRIEVER_VERIFY_SSL   "true"/"false" (default: true)
    KNOWLEDGE_RETRIEVER_ALLOW_PRIVATE "true"/"false" (default: false)
    MILVUS_URI / MILVUS_* + EMBEDDING_BACKEND  (for "milvus"; see milvus_retriever)

When the backend is "none" (the default), an ``UnconfiguredRetriever`` is
returned; it raises on use so unconfigured knowledge nodes fail loudly instead
of silently returning empty results.
"""

import os
import threading
from typing import Optional

from goalflow.config import get_logger
from goalflow.knowledge.base import KnowledgeRetriever, UnconfiguredRetriever

logger = get_logger(__name__)

_retriever: Optional[KnowledgeRetriever] = None
_lock = threading.Lock()


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _build_from_env() -> KnowledgeRetriever:
    backend = os.getenv("KNOWLEDGE_RETRIEVER_BACKEND", "none").strip().lower()

    if backend in ("", "none", "disabled"):
        return UnconfiguredRetriever("KNOWLEDGE_RETRIEVER_BACKEND is not set")

    if backend == "http":
        endpoint = os.getenv("KNOWLEDGE_RETRIEVER_ENDPOINT", "").strip()
        if not endpoint:
            return UnconfiguredRetriever(
                "KNOWLEDGE_RETRIEVER_BACKEND=http but KNOWLEDGE_RETRIEVER_ENDPOINT is unset"
            )
        # Imported lazily so the http backend's requests import isn't paid for
        # when knowledge retrieval is unused.
        from goalflow.knowledge.http_retriever import HttpKnowledgeRetriever

        read_timeout = float(os.getenv("KNOWLEDGE_RETRIEVER_TIMEOUT", "30") or 30)
        return HttpKnowledgeRetriever(
            endpoint=endpoint,
            api_key=os.getenv("KNOWLEDGE_RETRIEVER_API_KEY", "").strip(),
            timeout=(5.0, read_timeout),
            verify_ssl=_env_bool("KNOWLEDGE_RETRIEVER_VERIFY_SSL", True),
            block_private_hosts=not _env_bool("KNOWLEDGE_RETRIEVER_ALLOW_PRIVATE", False),
        )

    if backend == "milvus":
        # Lazy import: pymilvus is an optional dependency, only needed here.
        from goalflow.knowledge.milvus_retriever import MilvusKnowledgeRetriever

        try:
            return MilvusKnowledgeRetriever.from_env()
        except Exception as e:
            # Surface a clear "not usable" retriever rather than crashing startup;
            # it will raise with this reason when the node actually runs.
            return UnconfiguredRetriever(f"milvus backend init failed: {e}")

    logger.warning("unknown knowledge retriever backend", backend=backend)
    return UnconfiguredRetriever(f"unknown backend {backend!r}")


def get_retriever() -> KnowledgeRetriever:
    """Return the process-wide retriever, building it from env on first use."""
    global _retriever
    if _retriever is not None:
        return _retriever
    with _lock:
        if _retriever is None:
            _retriever = _build_from_env()
            logger.info("knowledge retriever initialized", backend=type(_retriever).__name__)
        return _retriever


def set_retriever(retriever: Optional[KnowledgeRetriever]) -> None:
    """Inject a custom retriever (or ``None`` to reset).

    Lets an embedding application register its own backend (vector store, Dify
    dataset API client, ...) without going through env configuration. Passing
    ``None`` clears the cache so the next ``get_retriever()`` rebuilds from env.
    """
    global _retriever
    with _lock:
        _retriever = retriever
