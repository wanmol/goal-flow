"""HTTP knowledge retrieval backend.

A concrete :class:`~goalflow.knowledge.base.KnowledgeRetriever` that queries an
external retrieval service over HTTP. This is the default real backend: it fits
the framework's Dify origin (where knowledge lives behind a service API), needs
no heavy vector-store dependency, and is configured purely from env.

Wire protocol (request JSON):
    {"query": "...", "dataset_ids": [...], "top_k": 5,
     "score_threshold": 0.5, "retrieval_mode": "multiple",
     "reranking_enable": false, "reranking_model": {...}}

Expected response JSON (tolerant of common shapes):
    {"records": [
        {"content": "...", "title": "...", "url": "...", "score": 0.83,
         "metadata": {...}}, ...]}
  Also accepts a top-level list, or {"data": [...]} / {"chunks": [...]}, and
  Dify-style {"content"/"segment": {"content": ...}, "document": {...}}.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import requests

from goalflow.config import get_logger
from goalflow.knowledge.base import (
    KnowledgeRetriever,
    KnowledgeRetrievalError,
    RetrievalConfig,
    RetrievedChunk,
)

logger = get_logger(__name__)


class HttpKnowledgeRetriever(KnowledgeRetriever):
    """Query an external retrieval service over HTTP.

    Args:
        endpoint: full URL of the retrieval endpoint (POST).
        api_key: optional bearer token sent as ``Authorization: Bearer ...``.
        timeout: (connect, read) timeout in seconds.
        verify_ssl: TLS verification toggle.
        block_private_hosts: reject endpoints resolving to private/loopback/
            link-local IPs (SSRF guard). Enabled by default.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str = "",
        timeout: tuple[float, float] = (5.0, 30.0),
        verify_ssl: bool = True,
        block_private_hosts: bool = True,
    ):
        if not endpoint:
            raise ValueError("HttpKnowledgeRetriever requires a non-empty endpoint")
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.block_private_hosts = block_private_hosts
        if block_private_hosts:
            self._assert_public_endpoint(endpoint)

    @staticmethod
    def _assert_public_endpoint(url: str) -> None:
        """Reject non-http(s) schemes and private/loopback/link-local targets.

        A coarse SSRF guard: the retrieval endpoint is operator-configured, but
        we still refuse to point at internal metadata/services by default.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"retrieval endpoint must be http(s), got {parsed.scheme!r}")
        host = parsed.hostname
        if not host:
            raise ValueError("retrieval endpoint has no host")
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as e:
            raise ValueError(f"cannot resolve retrieval host {host!r}: {e}") from e
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(
                    f"retrieval endpoint {host!r} resolves to a non-public address "
                    f"({ip}); set KNOWLEDGE_RETRIEVER_ALLOW_PRIVATE=true to override"
                )

    def retrieve(self, query: str, config: RetrievalConfig) -> list[RetrievedChunk]:
        payload = {
            "query": query,
            "dataset_ids": list(config.dataset_ids),
            "top_k": config.top_k,
            "score_threshold": config.score_threshold,
            "retrieval_mode": config.retrieval_mode,
            "reranking_enable": config.reranking_enable,
            "reranking_model": config.reranking_model,
            "metadata_filtering": config.metadata_filtering,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except requests.RequestException as e:
            raise KnowledgeRetrievalError(f"retrieval request failed: {e}") from e

        if resp.status_code >= 400:
            raise KnowledgeRetrievalError(
                f"retrieval service returned {resp.status_code}: {resp.text[:300]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise KnowledgeRetrievalError(
                f"retrieval service returned non-JSON body: {resp.text[:300]}"
            ) from e

        records = self._extract_records(data)
        chunks = [self._to_chunk(r) for r in records if isinstance(r, dict)]
        logger.info(
            "knowledge retrieval done",
            endpoint=self.endpoint,
            dataset_count=len(config.dataset_ids),
            returned=len(chunks),
        )
        return chunks

    @staticmethod
    def _extract_records(data) -> list:
        """Pull the record list out of the various response envelopes."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("records", "data", "chunks", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _to_chunk(record: dict) -> RetrievedChunk:
        """Map one response record into a RetrievedChunk, tolerating shapes.

        Handles both flat records and Dify-style nested ``segment``/``document``.
        """
        segment = record.get("segment") if isinstance(record.get("segment"), dict) else {}
        document = record.get("document") if isinstance(record.get("document"), dict) else {}

        content = (
            record.get("content")
            or segment.get("content")
            or record.get("text")
            or ""
        )
        title = (
            record.get("title")
            or document.get("name")
            or segment.get("document_name")
            or ""
        )
        url = record.get("url") or document.get("url") or ""
        score = record.get("score")
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        return RetrievedChunk(
            content=content,
            title=title,
            url=url,
            score=score,
            metadata=metadata,
        )
