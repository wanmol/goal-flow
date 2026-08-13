"""Pluggable text embedding layer.

Query-time vectorization for vector-store retrieval backends (e.g. Milvus).
Kept separate from ``goalflow.llm`` so retrieval can vectorize a query without
pulling in the chat-model machinery, and so the embedding provider is swappable
independently of the chat provider.

Backends are selected by env (see :func:`get_embedder`):
    EMBEDDING_BACKEND   "dashscope" | "openai"   (default: "dashscope")
"""

from abc import ABC, abstractmethod
from typing import Optional


class EmbeddingError(Exception):
    """Raised when embedding a text fails (provider error, misconfiguration)."""


class TextEmbedder(ABC):
    """Turns text into a dense vector. Must be safe to reuse across requests."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Return the embedding vector for a single query string.

        Raises:
            EmbeddingError: on provider failure or misconfiguration.
        """
        raise NotImplementedError

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts (for ingestion).

        Default implementation calls ``embed_query`` per text; providers that
        support batch APIs should override for efficiency.
        """
        return [self.embed_query(t) for t in texts]


class DashScopeEmbedder(TextEmbedder):
    """Embed via DashScope (Tongyi) ``TextEmbedding`` — the framework default.

    Reuses the already-required ``dashscope`` dependency and the DASHSCOPE_KEY
    the rest of the stack uses, so no new credential is needed.
    """

    def __init__(self, model: str = "text-embedding-v3", api_key: Optional[str] = None):
        import os

        self.model = model
        self.api_key = api_key or os.getenv("DASHSCOPE_KEY", "")
        if not self.api_key:
            raise EmbeddingError("DASHSCOPE_KEY is not set for DashScope embeddings")

    def embed_query(self, text: str) -> list[float]:
        from dashscope import TextEmbedding

        try:
            resp = TextEmbedding.call(
                model=self.model,
                input=text,
                api_key=self.api_key,
            )
        except Exception as e:  # network / SDK error
            raise EmbeddingError(f"DashScope embedding call failed: {e}") from e

        # DashScope returns status_code + output.embeddings[0].embedding
        if getattr(resp, "status_code", 200) != 200:
            raise EmbeddingError(
                f"DashScope embedding error {resp.status_code}: "
                f"{getattr(resp, 'message', '')}"
            )
        try:
            return resp.output["embeddings"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as e:
            raise EmbeddingError(f"unexpected DashScope embedding response: {resp}") from e

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        from dashscope import TextEmbedding

        vectors: list[list[float]] = []
        # DashScope caps batch size (25 for text-embedding-v*); chunk accordingly.
        batch_size = 25
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            try:
                resp = TextEmbedding.call(model=self.model, input=batch, api_key=self.api_key)
            except Exception as e:
                raise EmbeddingError(f"DashScope batch embedding call failed: {e}") from e
            if getattr(resp, "status_code", 200) != 200:
                raise EmbeddingError(
                    f"DashScope embedding error {resp.status_code}: {getattr(resp, 'message', '')}"
                )
            try:
                # Order by text_index so vectors align with input order.
                embeddings = sorted(resp.output["embeddings"], key=lambda e: e["text_index"])
                vectors.extend(e["embedding"] for e in embeddings)
            except (KeyError, TypeError) as e:
                raise EmbeddingError(f"unexpected DashScope batch response: {resp}") from e
        return vectors


class OpenAIEmbedder(TextEmbedder):
    """Embed via OpenAI/Azure using langchain-openai (already a dependency)."""

    def __init__(self, model: str = "text-embedding-3-small"):
        import os

        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as e:
            raise EmbeddingError("langchain-openai is required for OpenAI embeddings") from e

        api_key = os.getenv("OPENAI_KEY", "")
        if not api_key:
            raise EmbeddingError("OPENAI_KEY is not set for OpenAI embeddings")
        base_url = os.getenv("OPENAI_ENDPOINT") or None
        self._client = OpenAIEmbeddings(model=model, api_key=api_key, base_url=base_url)

    def embed_query(self, text: str) -> list[float]:
        try:
            return self._client.embed_query(text)
        except Exception as e:
            raise EmbeddingError(f"OpenAI embedding call failed: {e}") from e

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return self._client.embed_documents(texts)
        except Exception as e:
            raise EmbeddingError(f"OpenAI batch embedding call failed: {e}") from e


def get_embedder(backend: Optional[str] = None, model: Optional[str] = None) -> TextEmbedder:
    """Build an embedder from an explicit choice or env.

    Args:
        backend: "dashscope" | "openai"; defaults to EMBEDDING_BACKEND env (dashscope).
        model: override the provider's default embedding model.
    """
    import os

    backend = (backend or os.getenv("EMBEDDING_BACKEND", "dashscope")).strip().lower()
    if backend == "dashscope":
        return DashScopeEmbedder(model=model or os.getenv("EMBEDDING_MODEL", "text-embedding-v3"))
    if backend == "openai":
        return OpenAIEmbedder(model=model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    raise EmbeddingError(f"unknown embedding backend {backend!r}")
