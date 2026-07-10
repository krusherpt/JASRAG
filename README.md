# JAS RAG Architecture

JAS RAG is a local-first retrieval baseline. It uses SQLite FTS5 for keyword retrieval, stores both document-level and chunk-level indexes, then formats ranked chunks into LLM-ready context.

It does not use embeddings, a vector database, a reranker, or an external API.

## System overview

```mermaid
flowchart TD
    A["Markdown files"] --> C["KVIndex.add_file()"]
    B["PDF / EPUB / HTML / text"] --> B1["Converter"]
    B1 --> C

    C --> D["Extract title + metadata"]
    D --> E["Clean + chunk text"]

    E --> F["documents table"]
    E --> G["docs_fts index"]
    E --> H["chunks table"]
    E --> I["chunks_fts index"]

    J["User query"] --> K["KnowledgeVault.query()"]
    K --> L["ContextBuilder.build_with_search()"]
    L --> I
    I --> M["Ranked chunks"]
    M --> N["Dedupe chunks"]
    N --> O["Format context + sources"]
    O --> P["LLM-ready context"]

    J --> Q["KnowledgeVault.search()"]
    Q --> R["Librarian.select()"]
    R --> G
    G --> S["Ranked documents"]
```

## Main components

| Component | File | Role |
| --- | --- | --- |
| Orchestrator | `kv/__init__.py` | Public API that wires indexing, search, conversion, health, and context building |
| CLI | `kv/__main__.py` | Command entry point for indexing, querying, stats, health, and repair |
| SQLite index | `kv/sqlite/index.py` | Database schema, FTS5 indexes, file indexing, chunking, search, health, repair |
| Context builder | `kv/builder/context.py` | Converts ranked chunks or documents into structured LLM-ready context |
| Librarian | `kv/librarian/librarian.py` | Document-level search with simple intent/category/source heuristics |
| Converter | `kv/sources/converter.py` | Optional PDF, EPUB, HTML, text, and Markdown conversion into Markdown |
| Eval harness | `kv/eval_retrieval.py` | Golden-query retrieval checks for health, top-1, top-3, and empty results |

## Data model

```mermaid
erDiagram
    documents ||--o{ chunks : contains
    documents ||--o{ docs_fts : indexed_by
    chunks ||--o{ chunks_fts : indexed_by

    documents {
        integer id
        text path
        text filename
        text source_type
        text category
        text title
        text tags
        text checksum
        text created_at
        text updated_at
    }

    chunks {
        integer id
        integer document_id
        integer chunk_index
        text content
        integer start_line
        integer end_line
    }

    docs_fts {
        text document_id
        text path
        text source_type
        text category
        text title
        text content
        text tags
    }

    chunks_fts {
        text chunk_id
        text document_id
        text content
    }
```

## Indexing flow

```mermaid
sequenceDiagram
    participant User
    participant CLI as CLI / KnowledgeVault
    participant Index as KVIndex
    participant DB as SQLite FTS5

    User->>CLI: index file.md manual examples
    CLI->>Index: add_file(path, source_type, category)
    Index->>Index: read UTF-8 content
    Index->>Index: extract title
    Index->>Index: compute checksum
    Index->>DB: upsert documents row
    Index->>DB: replace docs_fts row
    Index->>Index: clean + classify + chunk
    Index->>DB: insert chunks
    Index->>DB: insert chunks_fts rows
    Index-->>CLI: indexed / unchanged
```

The checksum prevents unchanged files from being re-indexed. If a known file changes, old document and chunk FTS rows are removed before the new content is inserted.

## Query flow

```mermaid
sequenceDiagram
    participant User
    participant KV as KnowledgeVault
    participant Builder as ContextBuilder
    participant Index as KVIndex
    participant DB as SQLite FTS5

    User->>KV: query("how does chunk retrieval work")
    KV->>Builder: build_with_search(query, top_k, max_tokens)
    Builder->>Index: search_chunks(query, limit)
    Index->>Index: build FTS OR query
    Index->>DB: search chunks_fts MATCH query
    DB-->>Index: ranked chunk rows
    Index-->>Builder: chunks
    Builder->>Builder: keep at most 2 chunks per document
    Builder->>Builder: apply character budget
    Builder->>Builder: format metadata + sources
    Builder-->>KV: LLM-ready context
    KV-->>User: context
```

## Search flow

`query` and `search` are different paths:

- `query` searches chunks and returns formatted context.
- `search` searches documents and returns document metadata.

`search` uses `Librarian.select()`:

1. Detect simple intent from keywords.
2. Search priority categories first.
3. Search all documents.
4. Boost matches by source type, category, and title.
5. Deduplicate by path.
6. Return top documents.

## Retrieval behavior

JAS RAG builds FTS5 queries using OR logic across words. This favors recall over strict exact matching.

Example:

```text
how does chunk retrieval work
```

becomes:

```text
how OR does OR chunk OR retrieval OR work
```

SQLite FTS5 ranks the matching rows. The context builder over-fetches chunk candidates, then keeps a diverse set by allowing at most two chunks from the same document.

## Chunking behavior

The chunker is heuristic and intentionally simple:

1. Strip YAML frontmatter.
2. Strip HTML comments.
3. Normalize whitespace.
4. Classify content shape:
   - structured
   - list
   - flat PDF
   - narrative
   - flat/reference
5. Split by headings, sentences, line groups, or word windows depending on content shape.
6. Merge tiny chunks.
7. Hard-split pathological long chunks.

Default targets:

- approximate chunk size: 2000 characters
- overlap: 300 characters
- maximum chunk size: 4000 characters

## Health checks

`python3 -m kv health` reports:

- document count
- document FTS row count
- chunk count
- chunk FTS row count
- orphan document FTS rows
- orphan chunk FTS rows
- uncategorized documents
- oversized chunks
- max chunk character count

`python3 -m kv repair-health` removes FTS rows whose parent rows no longer exist.

## Evaluation

The eval harness checks retrieval against `kv/eval_queries.jsonl`.

It validates:

- health status
- top-1 match rate
- top-3 match rate
- empty-result behavior

Run:

```bash
python3 -m kv.eval_retrieval --strict
```

## Design tradeoffs

| Decision | Benefit | Cost |
| --- | --- | --- |
| SQLite FTS5 instead of vector DB | Local, inspectable, no API, low setup | Weaker semantic matching |
| Chunk-level retrieval for `query` | Better context precision | More moving parts than document-only search |
| Document-level `search` path | Useful for browsing matches | Different behavior from `query` |
| Character-based token estimate | No tokenizer dependency | Approximate budgets |
| Heuristic chunking | Simple and dependency-light | Not ideal for every document type |

## When to add vector search

Add vector search only after the baseline proves insufficient:

1. Build a golden-query eval set.
2. Confirm keyword retrieval fails important cases.
3. Confirm failures are semantic, not caused by missing text, poor chunking, or weak queries.
4. Add vector search as a separate retrieval path.
5. Compare FTS5, vector, and hybrid results with the same eval set.

Until then, the FTS5 baseline is easier to debug, explain, and publish.
