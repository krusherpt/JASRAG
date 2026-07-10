#!/usr/bin/env python3
"""
KV AI Librarian — Smart document selector for Knowledge Vault

Decides WHICH documents to retrieve based on query intent.
Uses FTS5 index + heuristics to select the most relevant sources.

Usage:
  from kv.librarian.librarian import Librarian
  lib = Librarian()
  docs = lib.select("sales letter framework", top_k=5)
"""

import sys
import re
from pathlib import Path
from typing import List, Dict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlite.index import KVIndex


# Intent patterns — maps query patterns to source priorities
INTENT_PATTERNS = {
    "sales_copy": {
        "keywords": ["sales", "copy", "landing", "cta", "headline", "convert", "persuade"],
        "priority_sources": ["obsidian", "sop", "prompt"],
        "priority_categories": ["copywriting"],
        "boost_title": True
    },
    "framework": {
        "keywords": ["framework", "sb7", "slips", "aida", "pas", "spiral", "model", "structure"],
        "priority_sources": ["obsidian"],
        "priority_categories": ["copywriting"],
        "boost_title": True
    },
    "technical": {
        "keywords": ["code", "api", "config", "setup", "install", "error", "debug"],
        "priority_sources": ["openclaw", "claude", "manual"],
        "priority_categories": ["technical"],
        "boost_title": False
    },
    "content_strategy": {
        "keywords": ["content", "strategy", "post", "thread", "social", "engagement", "hook"],
        "priority_sources": ["obsidian", "sop", "prompt"],
        "priority_categories": ["content", "copywriting"],
        "boost_title": True
    },
    "business": {
        "keywords": ["price", "pricing", "sell", "revenue", "customer", "market", "competitor"],
        "priority_sources": ["obsidian", "sop"],
        "priority_categories": ["business", "copywriting"],
        "boost_title": True
    },
    "product": {
        "keywords": ["worksheet", "product", "bundle", "etsy", "n8n", "workflow"],
        "priority_sources": ["sop", "manual", "n8n"],
        "priority_categories": ["products", "content"],
        "boost_title": True
    },
    "psychology": {
        "keywords": ["trigger", "emotion", "fear", "urgency", "scarcity", "fomo", "proof"],
        "priority_sources": ["obsidian"],
        "priority_categories": ["copywriting"],
        "boost_title": True
    }
}


class Librarian:
    """AI Librarian — selects documents based on query intent"""
    
    def __init__(self, index=None):
        self.index = index or KVIndex()
    
    def select(self, query: str, top_k: int = 5, verbose: bool = False) -> List[Dict]:
        """
        Select most relevant documents for a query.
        
        Steps:
        1. Detect intent (which category of knowledge)
        2. Search FTS5 with intent-aware boosting
        3. Rank and deduplicate
        4. Return top_k documents
        """
        # Step 1: Detect intent
        intent = self._detect_intent(query)
        
        if verbose:
            print(f"🔍 Intent detected: {intent['name']}")
            print(f"   Priority sources: {intent['priority_sources']}")
            print(f"   Priority categories: {intent['priority_categories']}")
        
        # Step 2: Search with intent awareness
        results = []
        
        # Search in priority categories first
        for category in intent['priority_categories']:
            cat_results = self.index.search(query, limit=top_k, category=category)
            results.extend(cat_results)
        
        # Then search all sources
        all_results = self.index.search(query, limit=top_k * 2)
        results.extend(all_results)
        
        # Step 3: Rank and deduplicate
        ranked = self._rank_results(results, intent, query)
        
        # Step 4: Return top_k
        return ranked[:top_k]
    
    def _detect_intent(self, query: str) -> Dict:
        """Detect query intent based on keywords"""
        query_lower = query.lower()
        
        best_match = None
        best_score = 0
        
        for intent_name, intent_config in INTENT_PATTERNS.items():
            score = 0
            for keyword in intent_config["keywords"]:
                if keyword in query_lower:
                    score += 1
            
            if score > best_score:
                best_score = score
                best_match = {"name": intent_name, **intent_config}
        
        # Default intent if no match
        if best_score == 0:
            best_match = {
                "name": "general",
                "keywords": [],
                "priority_sources": ["obsidian", "sop"],
                "priority_categories": [],
                "boost_title": False
            }
        
        return best_match
    
    def _rank_results(self, results: List[Dict], intent: Dict, query: str) -> List[Dict]:
        """Rank results based on relevance and intent"""
        seen = set()
        ranked = []
        
        for r in results:
            path = r.get('path', '')
            if path in seen:
                continue
            seen.add(path)
            
            score = 1.0  # Base score from FTS rank
            
            # Boost for priority sources
            if r.get('source_type') in intent.get('priority_sources', []):
                score *= 1.5
            
            # Boost for priority categories
            if r.get('category') in intent.get('priority_categories', []):
                score *= 1.3
            
            # Boost for title match
            if intent.get('boost_title'):
                title = (r.get('title', '') or '').lower()
                query_words = query.lower().split()
                for word in query_words:
                    if word in title:
                        score *= 1.2
                        break
            
            r['relevance_score'] = score
            ranked.append(r)
        
        # Sort by relevance score (descending)
        ranked.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return ranked
    
    def get_document(self, doc_id: int) -> Dict:
        """Get full document by ID"""
        conn = self.index.conn
        doc = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(doc) if doc else None
    
    def get_chunks(self, doc_id: int) -> List[Dict]:
        """Get all chunks for a document"""
        conn = self.index.conn
        chunks = conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,)
        ).fetchall()
        return [dict(c) for c in chunks]


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python librarian.py <query> [--verbose]")
        sys.exit(1)
    
    query = sys.argv[1]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    lib = Librarian()
    docs = lib.select(query, top_k=5, verbose=verbose)
    
    print(f"\n📚 Librarian found {len(docs)} documents for: '{query}'\n")
    for i, doc in enumerate(docs):
        print(f"[{i+1}] {doc.get('title', 'Untitled')}")
        print(f"    Source: {doc.get('source_type', 'unknown')} | Category: {doc.get('category', 'none')}")
        print(f"    Score: {doc.get('relevance_score', 0):.2f}")
        print(f"    Path: {doc.get('path', 'N/A')}")
        snippet = doc.get('snippet', '')
        if snippet:
            print(f"    Snippet: {snippet[:120]}...")
        print()
