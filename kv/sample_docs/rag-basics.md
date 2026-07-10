# RAG Basics

Retrieval augmented generation helps an assistant answer with local knowledge.

This sample project uses SQLite FTS5 for keyword retrieval. Documents are split into chunks. Queries search the chunk index first, then the context builder formats the top chunks for a language model.

Use this when you need a small local knowledge base without external services.
