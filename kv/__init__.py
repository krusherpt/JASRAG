#!/usr/bin/env python3
"""
Knowledge Vault — Main Orchestrator

Ties together all components:
- Sources (PDF/EPUB conversion)
- Obsidian Vault (SSOT)
- SQLite FTS5 (index)
- AI Librarian (document selector)
- Context Builder (LLM-ready output)

Usage:
  from kv import KnowledgeVault
  kv = KnowledgeVault()
  answer = kv.query("sales letter framework")
"""

import sys
from pathlib import Path
from typing import List, Dict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlite.index import KVIndex
from librarian.librarian import Librarian
from builder.context import ContextBuilder
from sources.converter import Converter


class KnowledgeVault:
    """Main orchestrator for the Knowledge Vault"""
    
    def __init__(self):
        self.index = KVIndex()
        self.librarian = Librarian(self.index)
        self.builder = ContextBuilder(self.index)
        self.converter = Converter()
    
    def query(self, query: str, top_k: int = 5, max_tokens: int = 4000) -> str:
        """
        Query the Knowledge Vault.
        
        Returns formatted context with relevant documents.
        """
        return self.builder.build_with_search(query, top_k, max_tokens)
    
    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """Search for documents"""
        return self.librarian.select(query, top_k)
    
    def index_file(self, path: str, source_type: str = "manual", 
                   category: str = None) -> dict:
        """Index a file"""
        return self.index.add_file(path, source_type, category)
    
    def index_directory(self, dir_path: str, source_type: str = "manual",
                        category: str = None) -> list:
        """Index all indexable files in a directory (recursive; xberg for docs)"""
        return self.index.add_directory(dir_path, source_type, category)
    
    def convert_and_index(self, input_path: str, source_type: str = "manual",
                          category: str = None) -> dict:
        """Convert a file to Markdown and index it"""
        # Convert
        result = self.converter.convert(input_path, source_type=source_type)
        
        if result.get("status") != "converted":
            return result
        
        # Index
        index_result = self.index.add_file(result["output"], source_type, category)
        
        return {
            "conversion": result,
            "indexing": index_result
        }
    
    def stats(self) -> Dict:
        """Get vault statistics"""
        return self.index.get_stats()

    def health(self) -> Dict:
        """Get vault health checks"""
        return self.index.health()

    def repair_health(self) -> Dict:
        """Repair safe index-health issues"""
        return self.index.repair_health()
    
    def close(self):
        """Close all connections"""
        self.index.close()


# CLI interface
if __name__ == "__main__":
    import json
    
    if len(sys.argv) < 2:
        print("Usage: python -m kv <command> [args]")
        print("Commands: query, search, index, index-dir, convert, stats, health, repair-health")
        sys.exit(1)
    
    cmd = sys.argv[1]
    kv = KnowledgeVault()
    
    try:
        if cmd == "query":
            query = " ".join(sys.argv[2:])
            result = kv.query(query)
            print(result)
        
        elif cmd == "search":
            query = " ".join(sys.argv[2:])
            results = kv.search(query)
            for i, r in enumerate(results):
                print(f"[{i+1}] {r.get('title', 'Untitled')}")
                print(f"    Source: {r.get('source_type')} | Category: {r.get('category')}")
                print(f"    Path: {r.get('path')}")
                print()
        
        elif cmd == "index":
            path = sys.argv[2]
            source_type = sys.argv[3] if len(sys.argv) > 3 else "manual"
            category = sys.argv[4] if len(sys.argv) > 4 else None
            result = kv.index_file(path, source_type, category)
            print(json.dumps(result, indent=2))
        
        elif cmd == "index-dir":
            dir_path = sys.argv[2]
            source_type = sys.argv[3] if len(sys.argv) > 3 else "manual"
            category = sys.argv[4] if len(sys.argv) > 4 else None
            results = kv.index_directory(dir_path, source_type, category)
            for r in results:
                print(f"{r['status']}: {Path(r['path']).name}")
        
        elif cmd == "convert":
            input_path = sys.argv[2]
            source_type = sys.argv[3] if len(sys.argv) > 3 else "manual"
            result = kv.convert_and_index(input_path, source_type)
            print(json.dumps(result, indent=2))
        
        elif cmd == "stats":
            stats = kv.stats()
            print(f"📊 Knowledge Vault Stats:")
            print(f"   Documents: {stats['total_documents']}")
            print(f"   Chunks: {stats['total_chunks']}")
            print(f"   By Source: {json.dumps(stats['by_source'], indent=6)}")
            print(f"   By Category: {json.dumps(stats['by_category'], indent=6)}")

        elif cmd == "health":
            print(json.dumps(kv.health(), indent=2, ensure_ascii=False))

        elif cmd == "repair-health":
            print(json.dumps(kv.repair_health(), indent=2, ensure_ascii=False))
        
        else:
            print(f"Unknown command: {cmd}")
    
    finally:
        kv.close()
