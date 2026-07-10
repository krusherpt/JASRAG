#!/usr/bin/env python3
"""
KV Context Builder — Format selected documents into LLM-ready context

Takes documents from the AI Librarian and builds a structured context
that maximizes relevance while staying within token limits.

Usage:
  from kv.builder.context import ContextBuilder
  builder = ContextBuilder()
  context = builder.build(docs, max_tokens=4000)
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlite.index import KVIndex


# Approximate tokens per character (English: ~4 chars/token)
CHARS_PER_TOKEN = 4


class ContextBuilder:
    """Build LLM-ready context from selected documents"""
    
    def __init__(self, index=None):
        self.index = index or KVIndex()
    
    def build(self, docs: List[Dict], query: str = "", 
              max_tokens: int = 4000, include_sources: bool = True) -> str:
        """
        Build context string from documents.
        
        Strategy:
        1. Calculate available tokens per document
        2. Extract most relevant chunks
        3. Format with metadata and citations
        4. Add source attribution
        """
        max_chars = max_tokens * CHARS_PER_TOKEN
        
        # Calculate tokens per document (proportional to relevance)
        total_score = sum(d.get('relevance_score', 1.0) for d in docs) or 1
        doc_budgets = []
        for doc in docs:
            score = doc.get('relevance_score', 1.0)
            budget = int((score / total_score) * max_chars * 0.8)  # 80% for content
            doc_budgets.append(max(budget, 500))  # Minimum 500 chars per doc
        
        # Build context
        parts = []
        used_chars = 0
        
        for i, (doc, budget) in enumerate(zip(docs, doc_budgets)):
            if used_chars >= max_chars:
                break
            
            # Get document content
            content = self._get_document_content(doc)
            if not content:
                continue
            
            # Truncate to budget
            if len(content) > budget:
                content = content[:budget] + "\n\n[...truncated...]"
            
            # Format with metadata
            formatted = self._format_document(doc, content, i + 1)
            parts.append(formatted)
            used_chars += len(formatted)
        
        # Build final context
        context = self._build_header(query) + "\n\n".join(parts)
        
        if include_sources:
            context += self._build_sources(docs)
        
        return context
    
    def build_with_search(self, query: str, top_k: int = 5, 
                          max_tokens: int = 4000) -> str:
        """Search and build context in one step"""
        chunks = self.index.search_chunks(query, limit=max(top_k * 6, 12))
        selected = self._dedupe_chunks(chunks, top_k)
        return self.build_chunks(selected, query, max_tokens)

    def build_chunks(self, chunks: List[Dict], query: str = "",
                     max_tokens: int = 4000, include_sources: bool = True) -> str:
        """Build context from ranked chunks instead of full documents."""
        max_chars = max_tokens * CHARS_PER_TOKEN
        parts = []
        used_chars = 0

        for i, chunk in enumerate(chunks, 1):
            remaining = max_chars - used_chars
            if remaining <= 0:
                break

            content = (chunk.get('content') or '').strip()
            if not content:
                continue
            budget = max(500, min(remaining - 300, max_chars // max(1, len(chunks))))
            if len(content) > budget:
                content = content[:budget] + "\n\n[...truncated...]"

            formatted = self._format_document(chunk, content, i)
            if used_chars + len(formatted) > max_chars and parts:
                break
            parts.append(formatted)
            used_chars += len(formatted)

        context = self._build_header(query)
        context += "\n\n".join(parts) if parts else "No matching sources found."

        if include_sources and parts:
            context += self._build_sources(chunks)

        return context

    def _dedupe_chunks(self, chunks: List[Dict], top_k: int) -> List[Dict]:
        """Keep diverse chunks: at most two per document."""
        counts = {}
        selected = []
        for chunk in chunks:
            doc_id = chunk.get('document_id') or chunk.get('doc_id')
            if counts.get(doc_id, 0) >= 2:
                continue
            selected.append(chunk)
            counts[doc_id] = counts.get(doc_id, 0) + 1
            if len(selected) >= top_k:
                break
        return selected
    
    def _get_document_content(self, doc: Dict) -> str:
        """Get document content from database or file"""
        # Try to get from chunks first
        chunks = self.index.conn.execute(
            "SELECT content FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc.get('doc_id', doc.get('id', 0)),)
        ).fetchall()
        
        if chunks:
            return "\n\n".join(c['content'] for c in chunks)
        
        # Fallback: read from file
        path = doc.get('path', '')
        if path and Path(path).exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass
        
        # Use snippet as last resort
        return doc.get('snippet', '')
    
    def _format_document(self, doc: Dict, content: str, index: int) -> str:
        """Format a single document for context"""
        title = doc.get('title', 'Untitled')
        source = doc.get('source_type', 'unknown')
        category = doc.get('category', 'none')
        path = doc.get('path', '')
        chunk_index = doc.get('chunk_index')
        
        # Create header
        header = f"=== [{index}] {title} ==="
        meta = f"Source: {source} | Category: {category}"
        if chunk_index is not None:
            meta += f" | Chunk: {chunk_index}"
        
        # Clean content
        content = content.strip()
        
        # Format
        formatted = f"{header}\n{meta}\n{'─' * 40}\n{content}\n{'─' * 40}"
        
        return formatted
    
    def _build_header(self, query: str) -> str:
        """Build context header"""
        header = "=" * 60
        header += "\nKNOWLEDGE VAULT CONTEXT"
        header += "\n" + "=" * 60
        if query:
            header += f"\nQuery: {query}"
        header += "\n" + "=" * 60 + "\n\n"
        return header
    
    def _build_sources(self, docs: List[Dict]) -> str:
        """Build source attribution footer"""
        footer = "\n\n" + "=" * 60
        footer += "\n📚 SOURCES:"
        footer += "\n" + "=" * 60
        
        for i, doc in enumerate(docs):
            title = doc.get('title', 'Untitled')
            path = doc.get('path', 'N/A')
            footer += f"\n[{i+1}] {title}"
            footer += f"\n    {path}"
        
        footer += "\n" + "=" * 60
        return footer
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count"""
        return len(text) // CHARS_PER_TOKEN


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python context.py <query> [--max-tokens=4000]")
        sys.exit(1)
    
    query = sys.argv[1]
    max_tokens = 4000
    
    for arg in sys.argv[2:]:
        if arg.startswith("--max-tokens="):
            max_tokens = int(arg.split("=")[1])
    
    builder = ContextBuilder()
    context = builder.build_with_search(query, max_tokens=max_tokens)
    
    print(context)
    print(f"\n[Estimated tokens: {builder.estimate_tokens(context)}]")
