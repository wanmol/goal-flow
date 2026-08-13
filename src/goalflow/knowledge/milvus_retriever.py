"""Milvus vector-store knowledge retrieval backend.

A concrete :class:`~goalflow.knowledge.base.KnowledgeRetriever` that embeds the
query and runs a vector similarity search against Milvus collections.

``pymilvus`` is an OPTIONAL dependency: it is imported lazily so installs that
don't use Milvus pay nothing, and a missing install raises a clear error rather
than an ImportError at module load.

Mapping between the framework and Milvus:
- Each ``dataset_id`` in the node config maps to a Milvus collection. By default
  the collection name IS the dataset id; set MILVUS_COLLECTION to pin all
  datasets to one collection and filter by a dataset field instead.
- Result fields are read from configurable output fields (content/title/url),
  defaulting to "content"/"title"/"url".

Config (env):
    MILVUS_URI              e.g. http://localhost:19530  (or MILVUS_HOST/MILVUS_PORT)
    MILVUS_TOKEN            optional auth token (user:password or API key)
    MILVUS_DB              optional database name
    MILVUS_COLLECTION       optional single collection (overrides per-dataset)
    MILVUS_VECTOR_FIELD     vector field name          (default: "vector")
    MILVUS_CONTENT_FIELD    text field name            (default: "content")
    MILVUS_TITLE_FIELD      title field name           (default: "title")
    MILVUS_URL_FIELD        url field name             (default: "url")
    MILVUS_METRIC_TYPE      COSINE | L2 | IP           (default: "COSINE")
"""

import os
from typing import Any, Optional

from goalflow.config import get_logger
from goalflow.knowledge.base import (
    KnowledgeRetriever,
    KnowledgeRetrievalError,
    RetrievalConfig,
    RetrievedChunk,
)
from goalflow.knowledge.embedding import TextEmbedder, EmbeddingError, get_embedder

logger = get_logger(__name__)


class MilvusKnowledgeRetriever(KnowledgeRetriever):
    """Vector search over Milvus, one collection per dataset (by default).

    Args:
        uri: Milvus server URI (e.g. ``http://host:19530``).
        token: optional auth token (``user:password`` or API key).
        db_name: optional Milvus database.
        embedder: query vectorizer; defaults to the env-selected embedder.
        collection: pin all datasets to this single collection (optional).
        vector_field/content_field/title_field/url_field: schema field names.
        metric_type: similarity metric matching the collection's index.
    """

    def __init__(
        self,
        *,
        uri: str,
        token: str = "",
        db_name: str = "",
        embedder: Optional[TextEmbedder] = None,
        collection: Optional[str] = None,
        vector_field: str = "vector",
        content_field: str = "content",
        title_field: str = "title",
        url_field: str = "url",
        metric_type: str = "COSINE",
    ):
        if not uri:
            raise ValueError("MilvusKnowledgeRetriever requires a non-empty uri")
        self.uri = uri
        self.token = token
        self.db_name = db_name
        self.collection = collection
        self.vector_field = vector_field
        self.content_field = content_field
        self.title_field = title_field
        self.url_field = url_field
        self.metric_type = metric_type
        # Embedder is created eagerly so a misconfigured key fails at startup,
        # not on the first user query.
        self._embedder = embedder or get_embedder()
        self._client = self._connect()

    def _connect(self):
        """Create the MilvusClient, translating a missing dep into a clear error."""
        try:
            from pymilvus import MilvusClient
        except ImportError as e:
            raise KnowledgeRetrievalError(
                "pymilvus is not installed; run `pip install pymilvus` to use the "
                "milvus knowledge backend"
            ) from e

        kwargs: dict[str, Any] = {"uri": self.uri}
        if self.token:
            kwargs["token"] = self.token
        if self.db_name:
            kwargs["db_name"] = self.db_name
        try:
            return MilvusClient(**kwargs)
        except Exception as e:
            raise KnowledgeRetrievalError(f"failed to connect to Milvus at {self.uri}: {e}") from e

    def _collections_for(self, config: RetrievalConfig) -> list[str]:
        """Resolve which collections to search for this request."""
        if self.collection:
            return [self.collection]
        if config.dataset_ids:
            return list(config.dataset_ids)
        raise KnowledgeRetrievalError(
            "no dataset_ids configured and MILVUS_COLLECTION is unset; nothing to search"
        )

    def retrieve(self, query: str, config: RetrievalConfig) -> list[RetrievedChunk]:
        try:
            vector = self._embedder.embed_query(query)
        except EmbeddingError as e:
            raise KnowledgeRetrievalError(f"query embedding failed: {e}") from e

        output_fields = [self.content_field, self.title_field, self.url_field]
        search_params = {"metric_type": self.metric_type}
        # When pinned to a single collection but given dataset_ids, scope by a
        # dataset_id field so multiple logical datasets can share one collection.
        expr = None
        if self.collection and config.dataset_ids:
            ids = ", ".join(repr(d) for d in config.dataset_ids)
            expr = f"dataset_id in [{ids}]"

        collections = self._collections_for(config)
        hits: list[tuple[float, dict]] = []
        for coll in collections:
            try:
                results = self._client.search(
                    collection_name=coll,
                    data=[vector],
                    limit=config.top_k,
                    output_fields=output_fields,
                    search_params=search_params,
                    filter=expr or "",
                )
            except Exception as e:
                raise KnowledgeRetrievalError(
                    f"Milvus search failed on collection {coll!r}: {e}"
                ) from e
            # results is a list (one per query vector) of hit lists.
            for hit in (results[0] if results else []):
                score = hit.get("distance")
                entity = hit.get("entity", hit)
                hits.append((score if score is not None else 0.0, entity))

        # Merge across collections and keep the globally best top_k. For COSINE/IP
        # higher is better; for L2 lower is better.
        reverse = self.metric_type.upper() in ("COSINE", "IP")
        hits.sort(key=lambda h: h[0], reverse=reverse)

        chunks: list[RetrievedChunk] = []
        for score, entity in hits[: config.top_k]:
            if config.score_threshold is not None:
                # Threshold only meaningful for similarity (higher=better) metrics.
                if reverse and score < config.score_threshold:
                    continue
            chunks.append(
                RetrievedChunk(
                    content=entity.get(self.content_field, "") or "",
                    title=entity.get(self.title_field, "") or "",
                    url=entity.get(self.url_field, "") or "",
                    score=score,
                    metadata={
                        k: v
                        for k, v in entity.items()
                        if k not in (self.content_field, self.title_field, self.url_field)
                    },
                )
            )

        logger.info(
            "milvus retrieval done",
            collections=len(collections),
            returned=len(chunks),
            metric=self.metric_type,
        )
        return chunks

    @classmethod
    def from_env(cls, embedder: Optional[TextEmbedder] = None) -> "MilvusKnowledgeRetriever":
        """Construct from MILVUS_* environment variables."""
        uri = os.getenv("MILVUS_URI", "").strip()
        if not uri:
            host = os.getenv("MILVUS_HOST", "").strip()
            port = os.getenv("MILVUS_PORT", "19530").strip()
            if host:
                uri = f"http://{host}:{port}"
        if not uri:
            raise KnowledgeRetrievalError(
                "MILVUS_URI (or MILVUS_HOST) must be set for the milvus backend"
            )
        return cls(
            uri=uri,
            token=os.getenv("MILVUS_TOKEN", "").strip(),
            db_name=os.getenv("MILVUS_DB", "").strip(),
            embedder=embedder,
            collection=os.getenv("MILVUS_COLLECTION", "").strip() or None,
            vector_field=os.getenv("MILVUS_VECTOR_FIELD", "vector"),
            content_field=os.getenv("MILVUS_CONTENT_FIELD", "content"),
            title_field=os.getenv("MILVUS_TITLE_FIELD", "title"),
            url_field=os.getenv("MILVUS_URL_FIELD", "url"),
            metric_type=os.getenv("MILVUS_METRIC_TYPE", "COSINE"),
        )
