# JAS RAG

Just Another Simple RAG.

JAS RAG is a tiny local RAG baseline powered by SQLite FTS5. It indexes Markdown files into documents and chunks, retrieves ranked chunks, and formats LLM-ready context without embeddings, vector databases, or external APIs.

## Why this exists

Most RAG demos start with embeddings, API keys, hosted vector databases, and enough moving parts to make debugging retrieval harder than building it. JAS RAG starts with the smallest useful baseline:

- local-first storage
- deterministic keyword retrieval
- chunk-level search
- no API quota
- no private data included
- a small retrieval eval harness

Use it as a simple baseline before deciding whether vector search is actually needed.

## Features

- SQLite FTS5 document and chunk index
- Markdown indexing from a file or directory
- Optional PDF, EPUB, HTML, and text conversion to Markdown
- Chunk-aware context formatting for LLM prompts
- Lightweight health checks for index integrity
- Retrieval evaluation with golden queries
- Public sample docs for testing

## What this is not

JAS RAG is intentionally boring.

- No embeddings
- No vector database
- No reranker
- No chat UI
- No hosted service
- No private knowledge base data

Add those only after eval results prove the simple FTS5 baseline is the bottleneck.

## Repository layout

```text
kv/
  __main__.py              CLI entry point
  __init__.py              KnowledgeVault orchestrator
  sqlite/index.py          SQLite tables, FTS5 indexes, chunking, search
  builder/context.py       LLM-ready context builder
  librarian/librarian.py   Intent-aware document selector
  sources/converter.py     PDF/EPUB/HTML/text to Markdown converter
  eval_retrieval.py        Retrieval eval harness
  eval_queries.jsonl       Golden-query eval set
  sample_docs/             Small public docs for smoke testing
```

## Requirements

- Python 3.10+
- SQLite with FTS5 support
- PyYAML

Optional converter dependencies:

- `pdfplumber` for PDF
- `ebooklib` and `beautifulsoup4` for EPUB
- `beautifulsoup4` for HTML

## Install

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For the basic Markdown workflow, no optional converter dependency is needed.

## Quick start

Index the included sample docs:

```bash
python3 -m kv index-dir kv/sample_docs manual examples
```

Query the vault:

```bash
python3 -m kv query "how does chunk retrieval work"
```

Check index health:

```bash
python3 -m kv health
```

Run retrieval eval:

```bash
python3 -m kv.eval_retrieval
```

Expected sample result:

```text
health: PASS
cases: 4 (3 scored)
top1: 3/3 (100%)
top3: 3/3 (100%)
empty: 1/1
```

## Commands

```bash
python3 -m kv query "search text"
python3 -m kv search "search text"
python3 -m kv index path/to/file.md manual examples
python3 -m kv index-dir path/to/docs manual examples
python3 -m kv stats
python3 -m kv health
python3 -m kv repair-health
python3 -m kv.eval_retrieval
```

### `query`

Returns formatted context for an LLM prompt.

```bash
python3 -m kv query "golden queries top1 top3 retrieval"
```

### `search`

Returns matching documents with metadata.

```bash
python3 -m kv search "index markdown files"
```

### `index`

Indexes one Markdown file.

```bash
python3 -m kv index path/to/file.md manual examples
```

Arguments:

- `path/to/file.md`: file to index
- `manual`: source type
- `examples`: optional category

### `index-dir`

Indexes all Markdown files under a directory.

```bash
python3 -m kv index-dir path/to/docs manual examples
```

### `health`

Reports lightweight integrity checks:

- document count
- chunk count
- orphan FTS rows
- uncategorized documents
- oversized chunks
- max chunk size

### `repair-health`

Removes FTS rows whose parent document or chunk no longer exists.

## Architecture

```text
Markdown / text / HTML / PDF / EPUB
        |
        v
  optional converter
        |
        v
  Markdown content
        |
        v
  KVIndex.add_file()
        |
        +--> documents table
        +--> docs_fts FTS5 index
        +--> chunks table
        +--> chunks_fts FTS5 index
        |
        v
  ContextBuilder.build_with_search()
        |
        v
  ranked chunks + source metadata
        |
        v
  LLM-ready context
```

The main API is `KnowledgeVault` in `kv/__init__.py`. It wires together:

- `KVIndex` for storage, indexing, chunking, search, health, and repair
- `ContextBuilder` for LLM-ready output
- `Librarian` for document-level search with simple intent heuristics
- `Converter` for optional source conversion

## Retrieval model

JAS RAG uses SQLite FTS5 with `porter unicode61` tokenization.

For `query`, retrieval happens at chunk level:

1. Build an FTS query from user words with OR logic.
2. Search `chunks_fts`.
3. Rank using SQLite FTS5 rank.
4. Over-fetch candidates.
5. Deduplicate to keep at most two chunks per document.
6. Format chunks with title, source type, category, chunk index, and source list.

This keeps the system explainable: if a result is bad, you can inspect the chunk and query directly.

## Evaluation

The eval harness lives in `kv/eval_retrieval.py`.

It checks:

- index health
- expected top-1 retrieval
- expected top-3 retrieval
- empty-result behavior

Cases live in `kv/eval_queries.jsonl`.

Run:

```bash
python3 -m kv.eval_retrieval
```

Strict mode for CI-style checks:

```bash
python3 -m kv.eval_retrieval --strict
```

JSON report:

```bash
python3 -m kv.eval_retrieval --json
```

## Data and privacy

This repository includes only small public sample docs. It intentionally excludes:

- private knowledge-base data
- SQLite database files
- local absolute paths
- workflow exports
- auth files
- API keys
- embedding files

The `.gitignore` excludes generated databases, Python caches, virtual environments, build outputs, and private converted vault output.

## Limitations

- Keyword retrieval can miss semantic matches when query terms differ from document terms.
- Token counting is an estimate based on characters, not a model tokenizer.
- Chunking is heuristic and optimized for simplicity.
- Optional converters require extra dependencies.
- There is no web UI or chat loop.

## When to add vector search

Do not add vector search by default. Add it when all three are true:

1. You have a golden-query eval set.
2. Keyword retrieval fails important cases.
3. The failed cases require semantic matching, not better chunking or better source text.

Until then, FTS5 is easier to inspect, debug, ship, and maintain.

## License

MIT
