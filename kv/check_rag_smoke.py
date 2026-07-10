#!/usr/bin/env python3
"""Assert-based smoke check for the active Knowledge Vault RAG path."""

from kv import KnowledgeVault


def main():
    kv = KnowledgeVault()
    try:
        health = kv.health()
        assert health["documents"] > 0
        assert health["chunks"] > 0
        assert health["orphan_docs_fts"] == 0
        assert health["orphan_chunks_fts"] == 0

        context = kv.query("how does chunk retrieval work", top_k=3, max_tokens=1200)
        assert "KNOWLEDGE VAULT CONTEXT" in context
        assert "Chunk:" in context
        assert "chunks" in context

        empty = kv.query("zzzxxy nonexistentquery", top_k=3, max_tokens=1200)
        assert "No matching sources found." in empty
    finally:
        kv.close()


if __name__ == "__main__":
    main()
    print("rag smoke ok")
