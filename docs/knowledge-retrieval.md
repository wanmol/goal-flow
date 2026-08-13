**English** | [简体中文](knowledge-retrieval.zh-CN.md)

# Knowledge Retrieval & Ingestion

GoalFlow ships a pluggable knowledge-retrieval layer plus a companion **ingestion tool** that turns your documents into searchable vectors. The two sides share the same collection schema and embedding model, so anything you ingest is immediately retrievable.

- **Retrieval** — the `KnowledgeRetrievalNode` embeds the node's query and asks a backend for the most relevant chunks. Which backend runs is decided by environment configuration.
- **Ingestion** — `python -m goalflow.knowledge.ingest` extracts text from files, chunks it, embeds each chunk, and inserts them into a Milvus collection.

## Retrieval backends

`goalflow.knowledge.factory.get_retriever()` builds a process-wide retriever from `KNOWLEDGE_RETRIEVER_BACKEND`:

| Backend | Value | Behavior |
| --- | --- | --- |
| **None** (default) | `none` | Returns an `UnconfiguredRetriever` that **raises on use**, so a misconfigured knowledge node fails loudly instead of silently returning empty results. |
| **HTTP** | `http` | Calls an external retrieval service (`KNOWLEDGE_RETRIEVER_ENDPOINT`). SSRF-guarded: private/link-local hosts are blocked unless `KNOWLEDGE_RETRIEVER_ALLOW_PRIVATE=true`. |
| **Milvus** | `milvus` | Embeds the query locally and runs a vector similarity search against Milvus. Requires `pip install pymilvus`. |

Applications can bypass env config entirely and inject a custom retriever with `goalflow.knowledge.set_retriever(...)`.

### Environment variables

```bash
# --- backend selector ---
KNOWLEDGE_RETRIEVER_BACKEND=milvus       # none | http | milvus

# --- http backend ---
KNOWLEDGE_RETRIEVER_ENDPOINT=https://kb.internal/retrieve
KNOWLEDGE_RETRIEVER_API_KEY=...          # optional bearer token
KNOWLEDGE_RETRIEVER_TIMEOUT=30           # read timeout seconds
KNOWLEDGE_RETRIEVER_VERIFY_SSL=true
KNOWLEDGE_RETRIEVER_ALLOW_PRIVATE=false  # allow private/link-local hosts

# --- milvus backend (also used by the ingestion tool) ---
MILVUS_URI=http://localhost:19530        # or MILVUS_HOST / MILVUS_PORT
MILVUS_TOKEN=user:password               # optional auth
MILVUS_DB=                               # optional database name
MILVUS_COLLECTION=docs                   # pin all datasets to one collection
MILVUS_VECTOR_FIELD=vector               # schema field names (defaults shown)
MILVUS_CONTENT_FIELD=content
MILVUS_TITLE_FIELD=title
MILVUS_URL_FIELD=url
MILVUS_METRIC_TYPE=COSINE                # COSINE | L2 | IP

# --- embedding (shared by retrieval + ingestion) ---
EMBEDDING_BACKEND=dashscope              # dashscope | openai
EMBEDDING_MODEL=text-embedding-v3
```

By default each `dataset_id` in the node config maps to a Milvus collection of the same name. Set `MILVUS_COLLECTION` to pin **all** datasets to one collection and filter by the `dataset_id` field instead — this is the layout the ingestion tool produces.

> **Match embedding models.** Retrieval and ingestion must use the **same** `EMBEDDING_MODEL` and `MILVUS_METRIC_TYPE`. Vectors from different models live in different spaces and won't match.

## The ingestion tool

`python -m goalflow.knowledge.ingest` runs the full pipeline: **extract → chunk → embed → create collection → insert**.

```bash
pip install pymilvus
export MILVUS_URI=http://localhost:19530

# ingest files and/or directories (directories are walked recursively)
python -m goalflow.knowledge.ingest --collection docs ./a.pdf ./notes/

# tag chunks with a dataset id and tune chunking
python -m goalflow.knowledge.ingest \
  --collection docs --dataset-id ds1 \
  --chunk-size 800 --chunk-overlap 100 \
  --embedding-backend dashscope \
  ./your_docs/
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `inputs` (positional) | — | One or more files or directories. Directories are walked recursively. |
| `--collection` | *(required)* | Target Milvus collection. |
| `--dataset-id` | `""` | Value stored in the `dataset_id` field of every chunk; use it to filter at retrieval time. |
| `--uri` | `$MILVUS_URI` / `$MILVUS_HOST` | Milvus URI. |
| `--chunk-size` | `800` | Max characters per chunk. |
| `--chunk-overlap` | `100` | Overlap characters between adjacent chunks. |
| `--embedding-backend` | `$EMBEDDING_BACKEND` | `dashscope` or `openai`. |

### Supported file types

Text extraction reuses the `DocExtractorNode` extractors, so the tool understands the same formats: **pdf, docx, md, txt, csv, xlsx, pptx, html, epub**, and more. A file that fails to extract is recorded as an error and **does not** abort the batch — the run reports `files / chunks / inserted / errors` at the end.

### Chunking

`chunk_text(text, chunk_size=800, chunk_overlap=100)` is boundary-aware: it prefers to split on paragraph and sentence boundaries, packs segments up to `chunk_size`, and carries `chunk_overlap` characters of context into the next chunk. A single segment longer than `chunk_size` is hard-split without dropping any content.

### Collection schema

On first insert the tool creates the collection (if missing) with a schema that **matches the Milvus retriever's field names**, an `AUTOINDEX` on the vector field, and a metric type matching `MILVUS_METRIC_TYPE`:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | INT64 | auto primary key |
| `vector` | FLOAT_VECTOR | dimension inferred from the embedder |
| `content` | VARCHAR | the chunk text |
| `title` | VARCHAR | source file name |
| `url` | VARCHAR | source file path |
| `dataset_id` | VARCHAR | the `--dataset-id` tag |

An existing collection is left untouched — the tool only inserts into it.

## Programmatic API

```python
from pathlib import Path
from goalflow.knowledge import MilvusIngestor, IngestConfig, chunk_text

cfg = IngestConfig.from_env(collection="docs", dataset_id="ds1")
ingestor = MilvusIngestor(cfg)              # embedder built from EMBEDDING_* env
result = ingestor.ingest_files([Path("a.pdf"), Path("notes/")])
print(result.files, result.chunks, result.inserted, result.errors)

# chunker is usable on its own
chunks = chunk_text(open("a.txt").read(), chunk_size=500, chunk_overlap=50)
```

`IngestConfig(...)` can also be constructed directly for full control over field names and metric type. Pass a custom `TextEmbedder` to `MilvusIngestor(cfg, embedder=...)` to override the env-selected backend.

## End-to-end

```bash
# 1. ingest
export MILVUS_URI=http://localhost:19530
export EMBEDDING_BACKEND=dashscope EMBEDDING_MODEL=text-embedding-v3
python -m goalflow.knowledge.ingest --collection docs --dataset-id ds1 ./your_docs/

# 2. enable retrieval against the same collection + model
export KNOWLEDGE_RETRIEVER_BACKEND=milvus
export MILVUS_COLLECTION=docs
# EMBEDDING_BACKEND / EMBEDDING_MODEL must stay identical to step 1
```

The `KnowledgeRetrievalNode` in your workflow now returns real chunks. See [nodes.md](nodes.md) for the node's config surface and [storage-and-config.md](storage-and-config.md) for the full environment-variable reference.
