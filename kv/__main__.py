#!/usr/bin/env python3
"""Knowledge Vault CLI entry point"""
import sys
from pathlib import Path

# Add kv parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kv import KnowledgeVault

if __name__ == "__main__":
    import json
    
    if len(sys.argv) < 2:
        print("Usage: python kv <command> [args]")
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
