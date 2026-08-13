[English](knowledge-retrieval.md) | **简体中文**

# 知识检索与入库

GoalFlow 内置一个可插拔的知识检索层,以及配套的**文档入库工具**——把文档转成可检索的向量。两侧共用同一套集合 schema 和 embedding 模型,因此入库的内容即刻可被检索到。

- **检索** —— `KnowledgeRetrievalNode` 对节点的 query 做 embedding,再向后端请求最相关的 chunk。用哪个后端由环境变量决定。
- **入库** —— `python -m goalflow.knowledge.ingest` 从文件抽取文本、切分、逐块 embedding,并插入 Milvus 集合。

## 检索后端

`goalflow.knowledge.factory.get_retriever()` 根据 `KNOWLEDGE_RETRIEVER_BACKEND` 构建进程级检索器:

| 后端 | 取值 | 行为 |
| --- | --- | --- |
| **无**(默认) | `none` | 返回 `UnconfiguredRetriever`,**一使用就抛错**——让配置错误的知识节点显式失败,而不是静默返回空结果。 |
| **HTTP** | `http` | 调用外部检索服务(`KNOWLEDGE_RETRIEVER_ENDPOINT`)。带 SSRF 防护:默认拦截私网/link-local 主机,除非设 `KNOWLEDGE_RETRIEVER_ALLOW_PRIVATE=true`。 |
| **Milvus** | `milvus` | 本地对 query 做 embedding,再对 Milvus 做向量相似度检索。需 `pip install pymilvus`。 |

应用也可完全绕过环境变量,用 `goalflow.knowledge.set_retriever(...)` 注入自定义检索器。

### 环境变量

```bash
# --- 后端选择 ---
KNOWLEDGE_RETRIEVER_BACKEND=milvus       # none | http | milvus

# --- http 后端 ---
KNOWLEDGE_RETRIEVER_ENDPOINT=https://kb.internal/retrieve
KNOWLEDGE_RETRIEVER_API_KEY=...          # 可选 bearer token
KNOWLEDGE_RETRIEVER_TIMEOUT=30           # 读超时(秒)
KNOWLEDGE_RETRIEVER_VERIFY_SSL=true
KNOWLEDGE_RETRIEVER_ALLOW_PRIVATE=false  # 是否放行私网/link-local 主机

# --- milvus 后端(入库工具同样使用)---
MILVUS_URI=http://localhost:19530        # 或 MILVUS_HOST / MILVUS_PORT
MILVUS_TOKEN=user:password               # 可选鉴权
MILVUS_DB=                               # 可选数据库名
MILVUS_COLLECTION=docs                   # 把所有 dataset 固定到同一集合
MILVUS_VECTOR_FIELD=vector               # schema 字段名(下为默认值)
MILVUS_CONTENT_FIELD=content
MILVUS_TITLE_FIELD=title
MILVUS_URL_FIELD=url
MILVUS_METRIC_TYPE=COSINE                # COSINE | L2 | IP

# --- embedding(检索 + 入库共用)---
EMBEDDING_BACKEND=dashscope              # dashscope | openai
EMBEDDING_MODEL=text-embedding-v3
```

默认情况下,节点配置里的每个 `dataset_id` 映射到一个同名 Milvus 集合。设置 `MILVUS_COLLECTION` 可把**所有** dataset 固定到同一集合,改用 `dataset_id` 字段过滤——这正是入库工具产出的布局。

> **embedding 模型必须一致。** 检索与入库必须使用**相同**的 `EMBEDDING_MODEL` 和 `MILVUS_METRIC_TYPE`。不同模型的向量处于不同空间,无法匹配。

## 入库工具

`python -m goalflow.knowledge.ingest` 跑完整流水线:**抽取 → 切分 → embedding → 建集合 → 插入**。

```bash
pip install pymilvus
export MILVUS_URI=http://localhost:19530

# 入库文件和/或目录(目录递归遍历)
python -m goalflow.knowledge.ingest --collection docs ./a.pdf ./notes/

# 给 chunk 打 dataset 标签,并调整切分
python -m goalflow.knowledge.ingest \
  --collection docs --dataset-id ds1 \
  --chunk-size 800 --chunk-overlap 100 \
  --embedding-backend dashscope \
  ./your_docs/
```

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `inputs`(位置参数) | — | 一个或多个文件或目录。目录递归遍历。 |
| `--collection` | *(必填)* | 目标 Milvus 集合。 |
| `--dataset-id` | `""` | 写入每个 chunk 的 `dataset_id` 字段值;检索时用它过滤。 |
| `--uri` | `$MILVUS_URI` / `$MILVUS_HOST` | Milvus URI。 |
| `--chunk-size` | `800` | 每个 chunk 的最大字符数。 |
| `--chunk-overlap` | `100` | 相邻 chunk 之间的重叠字符数。 |
| `--embedding-backend` | `$EMBEDDING_BACKEND` | `dashscope` 或 `openai`。 |

### 支持的文件类型

文本抽取复用 `DocExtractorNode` 的抽取器,因此支持相同的格式:**pdf、docx、md、txt、csv、xlsx、pptx、html、epub** 等。抽取失败的文件会记为一条 error 而**不会**中断整批——运行结束会汇报 `files / chunks / inserted / errors`。

### 切分

`chunk_text(text, chunk_size=800, chunk_overlap=100)` 是边界感知的:优先在段落、句子边界处切分,按 `chunk_size` 打包,并把 `chunk_overlap` 个字符的上下文带入下一个 chunk。超过 `chunk_size` 的单个片段会硬切,且不丢任何内容。

### 集合 schema

首次插入时,若集合不存在则自动创建,schema **与 Milvus 检索器的字段名一致**,向量字段建 `AUTOINDEX`,metric 与 `MILVUS_METRIC_TYPE` 匹配:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INT64 | 自增主键 |
| `vector` | FLOAT_VECTOR | 维度由 embedder 推断 |
| `content` | VARCHAR | chunk 文本 |
| `title` | VARCHAR | 源文件名 |
| `url` | VARCHAR | 源文件路径 |
| `dataset_id` | VARCHAR | `--dataset-id` 标签 |

已存在的集合不会被改动——工具只往里插入。

## 编程接口

```python
from pathlib import Path
from goalflow.knowledge import MilvusIngestor, IngestConfig, chunk_text

cfg = IngestConfig.from_env(collection="docs", dataset_id="ds1")
ingestor = MilvusIngestor(cfg)              # embedder 由 EMBEDDING_* 环境变量构建
result = ingestor.ingest_files([Path("a.pdf"), Path("notes/")])
print(result.files, result.chunks, result.inserted, result.errors)

# 切分器可单独使用
chunks = chunk_text(open("a.txt").read(), chunk_size=500, chunk_overlap=50)
```

也可直接构造 `IngestConfig(...)` 以完全控制字段名和 metric。给 `MilvusIngestor(cfg, embedder=...)` 传入自定义 `TextEmbedder` 可覆盖环境变量选定的后端。

## 端到端

```bash
# 1. 入库
export MILVUS_URI=http://localhost:19530
export EMBEDDING_BACKEND=dashscope EMBEDDING_MODEL=text-embedding-v3
python -m goalflow.knowledge.ingest --collection docs --dataset-id ds1 ./your_docs/

# 2. 对同一集合 + 模型启用检索
export KNOWLEDGE_RETRIEVER_BACKEND=milvus
export MILVUS_COLLECTION=docs
# EMBEDDING_BACKEND / EMBEDDING_MODEL 必须与步骤 1 完全一致
```

此时工作流里的 `KnowledgeRetrievalNode` 会返回真实的 chunk。节点配置见 [nodes.zh-CN.md](nodes.zh-CN.md),完整环境变量见 [storage-and-config.zh-CN.md](storage-and-config.zh-CN.md)。
