# JAS RAG

Just Another Simple RAG.

JAS RAG is a tiny local RAG baseline powered by SQLite FTS5. It indexes Markdown files into documents + chunks, retrieves ranked chunks, and formats LLM-ready context. No vector database or external API is required.

## Quick start

```bash
python3 -m kv index-dir kv/sample_docs manual examples
python3 -m kv query "how does chunk retrieval work"
python3 -m kv health
python3 -m kv.eval_retrieval
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
```

## What is included

- SQLite FTS5 document and chunk index
- Chunk-level retrieval context builder
- Health checks for orphan FTS rows and oversized chunks
- Minimal retrieval eval harness
- Small public sample docs

## What is intentionally excluded

- Private knowledge-base data
- SQLite databases
- Embeddings
- Local absolute paths
- Workflow exports or private auth files

## Evaluation

```bash
python3 -m kv.eval_retrieval
```

The eval file is [kv/eval_queries.jsonl](kv/eval_queries.jsonl). It checks expected title/source/category/content matches and empty-query behavior.

## Notes

This is a simple FTS5 baseline. Add vector search only after a golden-query eval set proves keyword retrieval is the bottleneck.
