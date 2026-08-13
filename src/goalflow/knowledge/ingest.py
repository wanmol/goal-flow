"""Document ingestion for the Milvus knowledge backend.

Companion to :mod:`goalflow.knowledge.milvus_retriever`: turns files into
searchable vectors so the knowledge-retrieval node has something to find.

Pipeline:  file bytes --extract--> text --chunk--> chunks --embed--> vectors
           --insert--> Milvus collection

The collection schema and field names match what
:class:`~goalflow.knowledge.milvus_retriever.MilvusKnowledgeRetriever` reads, so
a collection created here is immediately searchable by the same env config.

Run as a CLI:
    python -m goalflow.knowledge.ingest --collection docs ./a.pdf ./b.md
    python -m goalflow.knowledge.ingest --collection docs --dataset-id ds1 ./notes/

``pymilvus`` is imported lazily (optional dependency).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from goalflow.config import get_logger
from goalflow.knowledge.embedding import TextEmbedder, get_embedder

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

def chunk_text(
    text: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[str]:
    """Split text into overlapping chunks, preferring natural boundaries.

    Splits on paragraph/sentence boundaries where possible so a chunk doesn't
    cut mid-sentence, then packs pieces up to ``chunk_size`` characters with
    ``chunk_overlap`` characters of trailing context carried into the next chunk.

    Args:
        text: source text.
        chunk_size: target max characters per chunk.
        chunk_overlap: characters of overlap between consecutive chunks.

    Returns:
        Non-empty chunk strings in document order.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    text = (text or "").strip()
    if not text:
        return []

    # Coarse split on blank lines / newlines / sentence enders, keeping order.
    import re

    pieces = re.split(r"(\n\s*\n|\n|(?<=[.!?。！？])\s+)", text)
    # Re-merge separators back onto content so nothing is lost.
    segments = ["".join(pieces[i:i + 2]) for i in range(0, len(pieces), 2)]
    segments = [s for s in (seg.strip() for seg in segments) if s]

    chunks: list[str] = []
    current = ""
    for seg in segments:
        if not current:
            current = seg
        elif len(current) + 1 + len(seg) <= chunk_size:
            current = f"{current} {seg}"
        else:
            chunks.append(current)
            # Start the next chunk with the overlap tail of the previous one.
            tail = current[-chunk_overlap:] if chunk_overlap else ""
            current = f"{tail} {seg}".strip() if tail else seg
        # A single oversized segment is hard-split.
        while len(current) > chunk_size:
            chunks.append(current[:chunk_size])
            carry = current[chunk_size - chunk_overlap:] if chunk_overlap else current[chunk_size:]
            current = carry
    if current.strip():
        chunks.append(current.strip())
    return chunks


def extract_text_from_file(path: Path) -> str:
    """Extract plain text from a file by extension, reusing the doc extractor."""
    # Reuse the node's extractor helpers so ingestion supports the same formats.
    from goalflow.node.doc_extractor_node import _extract_text_by_file_extension

    content = path.read_bytes()
    return _extract_text_by_file_extension(
        file_content=content, file_extension=path.suffix.lower()
    )


# --------------------------------------------------------------------------
# Ingestion into Milvus
# --------------------------------------------------------------------------

@dataclass
class IngestConfig:
    """Configuration for a Milvus ingestion run.

    Field names mirror the retriever's env defaults so a collection built here is
    searchable with matching MILVUS_* settings.
    """

    collection: str
    uri: str = ""
    token: str = ""
    db_name: str = ""
    dataset_id: Optional[str] = None
    chunk_size: int = 800
    chunk_overlap: int = 100
    vector_field: str = "vector"
    content_field: str = "content"
    title_field: str = "title"
    url_field: str = "url"
    dataset_field: str = "dataset_id"
    metric_type: str = "COSINE"
    id_field: str = "id"

    @classmethod
    def from_env(cls, collection: str, **overrides) -> "IngestConfig":
        base = dict(
            collection=collection,
            uri=os.getenv("MILVUS_URI", "").strip()
            or (
                f"http://{os.getenv('MILVUS_HOST','').strip()}:{os.getenv('MILVUS_PORT','19530').strip()}"
                if os.getenv("MILVUS_HOST")
                else ""
            ),
            token=os.getenv("MILVUS_TOKEN", "").strip(),
            db_name=os.getenv("MILVUS_DB", "").strip(),
            vector_field=os.getenv("MILVUS_VECTOR_FIELD", "vector"),
            content_field=os.getenv("MILVUS_CONTENT_FIELD", "content"),
            title_field=os.getenv("MILVUS_TITLE_FIELD", "title"),
            url_field=os.getenv("MILVUS_URL_FIELD", "url"),
            metric_type=os.getenv("MILVUS_METRIC_TYPE", "COSINE"),
        )
        base.update(overrides)
        return cls(**base)


@dataclass
class IngestResult:
    files: int = 0
    chunks: int = 0
    inserted: int = 0
    errors: list[str] = field(default_factory=list)


class MilvusIngestor:
    """Create/populate a Milvus collection from documents."""

    def __init__(self, config: IngestConfig, embedder: Optional[TextEmbedder] = None):
        if not config.uri:
            raise ValueError("IngestConfig.uri (or MILVUS_URI/MILVUS_HOST) is required")
        self.config = config
        self.embedder = embedder or get_embedder()
        self._client = self._connect()

    def _connect(self):
        try:
            from pymilvus import MilvusClient
        except ImportError as e:
            raise RuntimeError(
                "pymilvus is not installed; run `pip install pymilvus` to ingest into Milvus"
            ) from e
        kwargs = {"uri": self.config.uri}
        if self.config.token:
            kwargs["token"] = self.config.token
        if self.config.db_name:
            kwargs["db_name"] = self.config.db_name
        return MilvusClient(**kwargs)

    def ensure_collection(self, dim: int) -> None:
        """Create the collection with the retriever-compatible schema if absent."""
        from pymilvus import DataType

        c = self.config
        if self._client.has_collection(c.collection):
            logger.info("milvus collection exists", collection=c.collection)
            return

        schema = self._client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(c.id_field, DataType.INT64, is_primary=True)
        schema.add_field(c.vector_field, DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field(c.content_field, DataType.VARCHAR, max_length=65535)
        schema.add_field(c.title_field, DataType.VARCHAR, max_length=1024)
        schema.add_field(c.url_field, DataType.VARCHAR, max_length=2048)
        schema.add_field(c.dataset_field, DataType.VARCHAR, max_length=256)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name=c.vector_field,
            index_type="AUTOINDEX",
            metric_type=c.metric_type,
        )
        self._client.create_collection(
            collection_name=c.collection,
            schema=schema,
            index_params=index_params,
        )
        logger.info("milvus collection created", collection=c.collection, dim=dim)

    def ingest_files(self, paths: Iterable[Path]) -> IngestResult:
        """Extract, chunk, embed and insert each file. Returns a summary."""
        c = self.config
        result = IngestResult()
        rows: list[dict] = []
        pending_texts: list[str] = []

        for path in paths:
            try:
                text = extract_text_from_file(path)
            except Exception as e:
                result.errors.append(f"{path}: extract failed: {e}")
                logger.warning("ingest extract failed", path=str(path), error=str(e))
                continue
            chunks = chunk_text(
                text, chunk_size=c.chunk_size, chunk_overlap=c.chunk_overlap
            )
            result.files += 1
            result.chunks += len(chunks)
            for ch in chunks:
                pending_texts.append(ch)
                rows.append({
                    c.content_field: ch,
                    c.title_field: path.name,
                    c.url_field: str(path),
                    c.dataset_field: c.dataset_id or c.collection,
                })

        if not rows:
            logger.info("nothing to ingest", errors=len(result.errors))
            return result

        # Embed all chunks (batched) and attach vectors.
        vectors = self.embedder.embed_documents(pending_texts)
        if len(vectors) != len(rows):
            raise RuntimeError(
                f"embedding count {len(vectors)} != chunk count {len(rows)}"
            )
        dim = len(vectors[0])
        self.ensure_collection(dim)
        for row, vec in zip(rows, vectors):
            row[c.vector_field] = vec

        # Insert in batches to bound request size.
        batch = 256
        for start in range(0, len(rows), batch):
            self._client.insert(collection_name=c.collection, data=rows[start:start + batch])
            result.inserted += len(rows[start:start + batch])
        logger.info(
            "ingest complete",
            collection=c.collection,
            files=result.files,
            chunks=result.chunks,
            inserted=result.inserted,
            errors=len(result.errors),
        )
        return result


def _iter_paths(inputs: list[str]) -> list[Path]:
    """Expand file/dir inputs into a flat list of files."""
    out: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(f for f in p.rglob("*") if f.is_file()))
        elif p.is_file():
            out.append(p)
        else:
            logger.warning("ingest input not found", path=raw)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m goalflow.knowledge.ingest",
        description="Ingest documents into a Milvus collection for knowledge retrieval.",
    )
    parser.add_argument("inputs", nargs="+", help="file(s) or directory(ies) to ingest")
    parser.add_argument("--collection", required=True, help="target Milvus collection")
    parser.add_argument("--dataset-id", default=None, help="dataset_id tag stored on each chunk")
    parser.add_argument("--uri", default=None, help="Milvus URI (overrides MILVUS_URI)")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--embedding-backend", default=None, help="dashscope | openai")
    args = parser.parse_args(argv)

    cfg = IngestConfig.from_env(
        args.collection,
        dataset_id=args.dataset_id,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    if args.uri:
        cfg.uri = args.uri
    if not cfg.uri:
        parser.error("Milvus URI required: pass --uri or set MILVUS_URI / MILVUS_HOST")

    embedder = get_embedder(backend=args.embedding_backend) if args.embedding_backend else None
    paths = _iter_paths(args.inputs)
    if not paths:
        parser.error("no input files found")

    ingestor = MilvusIngestor(cfg, embedder=embedder)
    result = ingestor.ingest_files(paths)
    print(
        f"ingested {result.inserted} chunks from {result.files} file(s) "
        f"into '{cfg.collection}'"
        + (f"; {len(result.errors)} error(s)" if result.errors else "")
    )
    for err in result.errors:
        print(f"  - {err}")
    return 1 if result.errors and result.inserted == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
