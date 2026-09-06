#!/usr/bin/env python3
"""
KV SQLite FTS5 Index — Full Text Search engine for Knowledge Vault

Usage:
  from kv.sqlite.index import KVIndex
  idx = KVIndex()
  idx.add_file("path/to/file.md")
  idx.search("query", limit=5)
"""

import sqlite3
import os
import re
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime

DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "kv.db"

# Directories never worth descending into
EXCLUDE_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules",
                ".venv", "venv", ".idea", ".vscode", "dist", "build",
                ".extracted", ".cache", ".obsidian"}

# Binary / archive / media extensions that are never indexed
EXCLUDE_EXTENSIONS = {
    # archives
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".zst",
    # images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".ico", ".heic",
    # audio/video
    ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".mp4", ".mkv", ".avi",
    ".mov", ".webm",
    # fonts
    ".ttf", ".otf", ".woff", ".woff2",
    # executables & compiled
    ".exe", ".dll", ".so", ".dylib", ".pyc", ".class", ".o", ".a", ".bin",
    # databases
    ".db", ".sqlite", ".sqlite3",
}

class KVIndex:
    """SQLite FTS5 index for Knowledge Vault"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        """Initialize FTS5 tables"""
        self.conn.executescript("""
            -- Documents table (metadata)
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                source_type TEXT NOT NULL,  -- obsidian, pdf, epub, sop, prompt, n8n, openclaw, claude, manual
                category TEXT,             -- copywriting, business, content, technical
                title TEXT,
                tags TEXT,                 -- comma-separated
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                checksum TEXT              -- for change detection
            );
            
            -- FTS5 index (full-text search)
            CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
                document_id UNINDEXED,
                path UNINDEXED,
                source_type UNINDEXED,
                category UNINDEXED,
                title,
                content,
                tags,
                tokenize='porter unicode61'
            );
            
            -- Chunks table (for large documents)
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );
            
            -- FTS5 for chunks
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                content,
                tokenize='porter unicode61'
            );
        """)
        self.conn.commit()
    
    # Formats that benefit from xberg's conversion even though they're text
    HTML_EXTENSIONS = {".html", ".htm", ".xhtml"}

    def _extract_text(self, path):
        """Extract searchable text from a file.

        - text/code files (no null bytes): read directly (fast)
        - HTML: xberg (tags stripped to clean markdown)
        - binaries (null bytes present): xberg (107+ formats)
        Returns str, or None if the file should be skipped.
        """
        p = Path(path)
        suffix = p.suffix.lower()

        if suffix in EXCLUDE_EXTENSIONS:
            return None

        try:
            raw = p.read_bytes()
        except OSError:
            return None

        # HTML goes through xberg for clean tag-stripped markdown
        if suffix in self.HTML_EXTENSIONS:
            return self._xberg_text(raw, p.name)

        # Null bytes => binary document (PDF, DOCX, EPUB, ...) => xberg
        if b"\x00" in raw:
            return self._xberg_text(raw, p.name)

        # Plain text/code: index directly
        return raw.decode("utf-8", errors="replace")

    def _xberg_text(self, raw: bytes, filename: str = ""):
        """Run xberg extraction over bytes; returns text or None on failure."""
        try:
            import xberg
            from xberg import ExtractInput, ExtractInputKind, ExtractionConfig
            result = asyncio.run(
                xberg.extract(ExtractInput(kind=ExtractInputKind.BYTES,
                                           bytes=raw, filename=filename),
                              ExtractionConfig(use_cache=False)))
            if result.results:
                return result.results[0].content or None
            return None
        except Exception:
            return None

    def add_file(self, path, source_type="manual", category=None, tags=None):
        """Add a file to the index (any supported format)"""
        path = str(Path(path).resolve())

        # Extract text content (xberg for documents, direct read for text)
        content = self._extract_text(path)
        if content is None:
            return {"status": "skipped", "path": path,
                    "reason": "unsupported or unreadable format"}

        # Extract metadata
        filename = Path(path).name
        title = self._extract_title(content, filename)
        checksum = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        # Check if already indexed (skip if unchanged)
        existing = self.conn.execute(
            "SELECT checksum FROM documents WHERE path = ?", (path,)
        ).fetchone()
        
        if existing and existing['checksum'] == checksum:
            return {"status": "unchanged", "path": path}
        
        # Upsert document
        if existing:
            self.conn.execute("""
                UPDATE documents SET 
                    filename = ?, source_type = ?, category = ?,
                    title = ?, tags = ?, checksum = ?, updated_at = ?
                WHERE path = ?
            """, (filename, source_type, category, title, tags, checksum, 
                  datetime.now().isoformat(), path))
            doc_id = self.conn.execute(
                "SELECT id FROM documents WHERE path = ?", (path,)
            ).fetchone()['id']
            # Clear old chunks
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM chunks_fts WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM docs_fts WHERE document_id = ?", (doc_id,))
        else:
            cursor = self.conn.execute("""
                INSERT INTO documents (path, filename, source_type, category, title, tags, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (path, filename, source_type, category, title, tags, checksum))
            doc_id = cursor.lastrowid
        
        # Add to FTS
        self.conn.execute("""
            INSERT INTO docs_fts (document_id, path, source_type, category, title, content, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, path, source_type, category, title, content, tags or ""))
        
        # Chunk and index
        chunks = self._chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_cursor = self.conn.execute("""
                INSERT INTO chunks (document_id, chunk_index, content, start_line, end_line)
                VALUES (?, ?, ?, ?, ?)
            """, (doc_id, i, chunk['text'], chunk.get('start_line'), chunk.get('end_line')))
            
            self.conn.execute("""
                INSERT INTO chunks_fts (chunk_id, document_id, content)
                VALUES (?, ?, ?)
            """, (chunk_cursor.lastrowid, doc_id, chunk['text']))
        
        self.conn.commit()
        
        return {
            "status": "indexed",
            "path": path,
            "doc_id": doc_id,
            "chunks": len(chunks)
        }
    
    def add_directory(self, dir_path, source_type="manual", category=None):
        """Add all indexable files in a directory (recursive).

        Text/code files are read directly; documents (PDF, DOCX, HTML,
        EPUB, ...) are extracted with xberg. Binaries, archives, and
        media files are skipped; .git and similar dirs are excluded.
        """
        results = []
        root = Path(dir_path)
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            # Skip excluded directories anywhere in the path
            rel_parts = file_path.relative_to(root).parts
            if any(part in EXCLUDE_DIRS for part in rel_parts):
                continue
            # Skip hidden files
            if file_path.name.startswith("."):
                continue
            # Skip excluded extensions
            if file_path.suffix.lower() in EXCLUDE_EXTENSIONS:
                continue
            result = self.add_file(file_path, source_type, category)
            results.append(result)
        return results
    
    def search(self, query, limit=5, source_type=None, category=None):
        """Full-text search across all documents"""
        if not query or not query.strip():
            return []
        # Build FTS query
        fts_query = self._build_fts_query(query)
        
        # Search in document content
        sql = """
            SELECT 
                d.id as doc_id,
                d.path,
                d.source_type,
                d.category,
                d.title,
                d.tags,
                snippet(docs_fts, 5, '<b>', '</b>', '...', 40) as snippet,
                rank
            FROM docs_fts
            JOIN documents d ON d.id = docs_fts.document_id
            WHERE docs_fts MATCH ?
        """
        params = [fts_query]
        
        if source_type:
            sql += " AND d.source_type = ?"
            params.append(source_type)
        if category:
            sql += " AND d.category = ?"
            params.append(category)
        
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        
        try:
            results = self.conn.execute(sql, params).fetchall()
            return [dict(r) for r in results]
        except Exception as e:
            # Fallback: simple LIKE search
            return self._fallback_search(query, limit, source_type, category)
    
    def search_chunks(self, query, limit=5):
        """Search within document chunks (for large documents)"""
        if not query or not query.strip():
            return []
        fts_query = self._build_fts_query(query)
        
        sql = """
            SELECT 
                c.document_id,
                c.chunk_index,
                c.content,
                c.start_line,
                c.end_line,
                d.id as doc_id,
                d.path,
                d.title,
                d.source_type,
                d.category,
                d.tags,
                rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        
        try:
            results = self.conn.execute(sql, [fts_query, limit]).fetchall()
            return [dict(r) for r in results]
        except:
            return []

    def health(self):
        """Return lightweight index integrity and chunk-quality stats."""
        row = self.conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM documents) AS documents,
                (SELECT COUNT(*) FROM docs_fts) AS docs_fts,
                (SELECT COUNT(*) FROM chunks) AS chunks,
                (SELECT COUNT(*) FROM chunks_fts) AS chunks_fts,
                (SELECT COUNT(*) FROM docs_fts f LEFT JOIN documents d ON d.id = f.document_id WHERE d.id IS NULL) AS orphan_docs_fts,
                (SELECT COUNT(*) FROM chunks_fts f LEFT JOIN chunks c ON c.id = f.chunk_id WHERE c.id IS NULL) AS orphan_chunks_fts,
                (SELECT COUNT(*) FROM documents WHERE category IS NULL OR category = '') AS uncategorized_documents,
                (SELECT COUNT(*) FROM chunks WHERE length(content) > 4000) AS oversized_chunks,
                (SELECT COALESCE(MAX(length(content)), 0) FROM chunks) AS max_chunk_chars
        """).fetchone()
        return dict(row)

    def repair_health(self):
        """Remove FTS rows whose parent rows no longer exist."""
        before = self.health()
        self.conn.execute("""
            DELETE FROM docs_fts
            WHERE document_id NOT IN (SELECT id FROM documents)
        """)
        self.conn.execute("""
            DELETE FROM chunks_fts
            WHERE chunk_id NOT IN (SELECT id FROM chunks)
        """)
        self.conn.commit()
        after = self.health()
        return {"before": before, "after": after}
    
    def _chunk_text(self, text, chunk_size=2000, overlap=300):
        """4-stage chunking: clean -> classify -> per-type split -> quality check."""
        import yaml
        from io import StringIO
        
        STAGE = 1
        # Stage 1: Clean
        # Strip YAML frontmatter
        body = text
        yaml_meta = {}
        if text.startswith('---'):
            parts = text.split('---', 2)
            if len(parts) >= 3:
                yaml_block = parts[1]
                try:
                    yaml_meta = yaml.safe_load(yaml_block) or {}
                except Exception:
                    pass
                body = parts[2]
        
        # Strip HTML comments
        body = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL)
        # Normalize whitespace
        body = re.sub(r'[ \t]+', ' ', body)
        body = re.sub(r'\n{3,}', '\n\n', body)
        body = body.strip()
        if not body:
            return []
        
        STAGE = 2
        # Stage 2: Classify content type
        headings = len(re.findall(r'^#{1,3}\s+', body, re.MULTILINE))
        lines = body.splitlines()
        list_lines = sum(1 for line in lines if re.match(r'^\s*(?:[-*]|\d+[.)])\s', line))
        list_ratio = list_lines / max(1, len(lines))
        paragraphs = [p for p in re.split(r'\n\s*\n', body) if p.strip()]
        
        # Detect flat PDF: very few paragraphs for the body size
        effective_paras = max(1, len(paragraphs))
        density = len(body) / effective_paras  # chars per paragraph
        
        if headings >= 3:
            kind = 'structured'
        elif list_ratio > 0.5:
            kind = 'list'
        elif len(paragraphs) <= 3 and list_ratio > 0.3:
            kind = 'list'
        elif density > 5000 and len(body) > 20000:
            # PDF flat text — 0 blank lines, everything 1 paragraph
            kind = 'flat_pdf'
        elif len(paragraphs) <= 3 and len(body) > 10000:
            # Few paragraphs, large body -> flat extraction
            kind = 'flat_pdf'
        elif len(body) < chunk_size * 3:
            kind = 'flat'
        elif headings == 0:
            kind = 'narrative'
        else:
            kind = 'structured'
        
        STAGE = 3
        # Stage 3: Chunk by type
        raw = []  # list of (title, text)
        title_fallback = yaml_meta.get('title', yaml_meta.get('chapter', ''))
        
        if kind == 'structured':
            # Split on ## headings
            parts = re.split(r'^(?=##+\s)', body, flags=re.MULTILINE)
            current = ''
            current_title = title_fallback
            for part in parts:
                if not part.strip():
                    continue
                hm = re.match(r'^(#+)\s+(.+)$', part, re.MULTILINE)
                if hm and len(hm.group(1)) >= 2:
                    if current:
                        raw.append((current_title, current.strip()))
                    current = part
                    current_title = hm.group(2).strip()
                else:
                    current += '\n\n' + part
            if current:
                raw.append((current_title, current.strip()))
        
        elif kind == 'narrative':
            # Sentence-boundary sliding window
            sents = re.split(r'(?<=[.!?])\s+', body)
            current = ''
            for sent in sents:
                if not sent.strip():
                    continue
                if len(current) + len(sent) > chunk_size and current:
                    raw.append((title_fallback, current.strip()))
                    # overlap from end
                    words = current.split()
                    overlap_words = max(1, overlap // 5)
                    current = ' '.join(words[-overlap_words:]) + ' '
                current += sent + ' '
            if current.strip():
                raw.append((title_fallback, current.strip()))
        
        elif kind == 'list':
            # Group list items under headings
            parts = re.split(r'^(?=##+\s)', body, flags=re.MULTILINE)
            current = ''
            current_title = title_fallback
            for part in parts:
                if not part.strip():
                    continue
                hm = re.match(r'^(#+)\s+(.+)$', part, re.MULTILINE)
                if hm:
                    if current:
                        raw.append((current_title, current.strip()))
                    current = part
                    current_title = hm.group(2).strip()
                    # check if heading + list already fits
                    if len(current) > chunk_size:
                        # split list items
                        items = [l for l in current.splitlines() if l.strip()]
                        grouped = []
                        g = []
                        gc = 0
                        for item in items:
                            if gc + len(item) > chunk_size and g:
                                grouped.append((current_title, '\n'.join(g)))
                                g = []
                                gc = 0
                            g.append(item)
                            gc += len(item)
                        if g:
                            grouped.append((current_title, '\n'.join(g)))
                        raw.extend(grouped)
                        current = ''
                else:
                    if len(current) + len(part) > chunk_size and current:
                        raw.append((current_title, current.strip()))
                        # overlap: keep some tail items
                        lines_parts = current.splitlines()
                        tail_count = max(1, overlap // 400)
                        tail_lines = lines_parts[-tail_count:] if len(lines_parts) > tail_count else lines_parts
                        current = '\n'.join(tail_lines) + '\n'
                    current += part + '\n'
            if current:
                raw.append((current_title, current.strip()))
        
        elif kind == 'flat_pdf':
            # PDF flat text: split on line boundaries (~30 lines per chunk)
            all_lines = body.splitlines()
            target_lines = max(8, chunk_size // 60)
            overlap_lines = max(1, overlap // 60)
            # Group lines, try to find natural sentence breaks
            i = 0
            while i < len(all_lines):
                end = min(i + target_lines, len(all_lines))
                chunk_text = '\n'.join(all_lines[i:end]).strip()
                if chunk_text:
                    raw.append((title_fallback, chunk_text))
                i += target_lines - overlap_lines
        
        else:  # flat / reference
            # Fixed-size split with word boundaries
            words_list = body.split()
            target_words = max(10, chunk_size // 5)
            overlap_words = max(2, overlap // 5)
            i = 0
            while i < len(words_list):
                end = min(i + target_words, len(words_list))
                chunk_text = ' '.join(words_list[i:end])
                raw.append((title_fallback, chunk_text))
                i += target_words - overlap_words
        
        STAGE = 4
        # Stage 4: Quality check
        MIN_CHUNK = 200
        MAX_CHUNK = 4000
        
        result = []
        carry = ''
        for title, content in raw:
            content = content.strip()
            if not content:
                continue
            combined = (carry + '\n\n' + content).strip() if carry else content
            carry = ''
            
            if len(combined) < MIN_CHUNK:
                carry = combined
                continue
            
            if len(combined) > MAX_CHUNK:
                for part in self._hard_split(combined, MAX_CHUNK, overlap):
                    if len(part) >= MIN_CHUNK:
                        result.append({'text': part, 'title': title})
                    elif result:
                        result[-1]['text'] += '\n\n' + part
                    else:
                        result.append({'text': part, 'title': title})
            else:
                result.append({'text': combined, 'title': title})
        
        if carry and result:
            result[-1]['text'] += '\n\n' + carry
        elif carry:
            result.append({'text': carry})
        
        return result

    def _hard_split(self, text, max_chars=4000, overlap=300):
        """Split pathological long chunks on word boundaries."""
        words = text.split()
        if not words:
            return []
        parts = []
        current = []
        current_len = 0
        for word in words:
            extra = len(word) + (1 if current else 0)
            if current and current_len + extra > max_chars:
                parts.append(' '.join(current))
                tail = ' '.join(current)[-overlap:].split()
                current = tail[:]
                current_len = len(' '.join(current))
            current.append(word)
            current_len += extra
        if current:
            parts.append(' '.join(current))
        return parts
    
    def _extract_title(self, content, fallback=""):
        """Extract title from markdown content"""
        # Try to find markdown heading
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        # Try YAML frontmatter
        match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return Path(fallback).stem
    
    def _build_fts_query(self, query):
        """Build FTS5 query with OR logic for better recall"""
        if not query or not query.strip():
            return ""
        words = re.findall(r'\w+', query.lower())
        if not words:
            return ""
        # Use OR for better recall
        return " OR ".join(words)
    
    def _fallback_search(self, query, limit, source_type, category):
        """Fallback LIKE search when FTS fails"""
        words = query.lower().split()
        if not words:
            return []
        conditions = [" LOWER(content) LIKE ? " for _ in words]
        params = [f"%{w}%" for w in words]
        
        sql = """
            SELECT 
                d.id as doc_id,
                d.path,
                d.source_type,
                d.category,
                d.title,
                substr(c.content, 1, 200) as snippet
            FROM documents d
            JOIN chunks c ON c.document_id = d.id
            WHERE """ + " AND ".join(conditions)
        
        if source_type:
            sql += " AND d.source_type = ?"
            params.append(source_type)
        if category:
            sql += " AND d.category = ?"
            params.append(category)
        
        sql += " LIMIT ?"
        params.append(limit)
        
        results = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in results]
    
    def get_stats(self):
        """Get index statistics"""
        stats = {}
        stats['total_documents'] = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        stats['total_chunks'] = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        
        # By source type
        rows = self.conn.execute("""
            SELECT source_type, COUNT(*) as count 
            FROM documents GROUP BY source_type
        """).fetchall()
        stats['by_source'] = {r['source_type']: r['count'] for r in rows}
        
        # By category
        rows = self.conn.execute("""
            SELECT category, COUNT(*) as count 
            FROM documents WHERE category IS NOT NULL
            GROUP BY category
        """).fetchall()
        stats['by_category'] = {r['category']: r['count'] for r in rows}
        
        return stats
    
    def close(self):
        """Close database connection"""
        self.conn.close()


# CLI interface
if __name__ == "__main__":
    import sys
    
    idx = KVIndex()
    
    if len(sys.argv) < 2:
        print("Usage: python index.py [stats|search|add|add-dir]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "stats":
        stats = idx.get_stats()
        print(f"📊 Knowledge Vault Index Stats:")
        print(f"   Documents: {stats['total_documents']}")
        print(f"   Chunks: {stats['total_chunks']}")
        print(f"   By Source: {stats['by_source']}")
        print(f"   By Category: {stats['by_category']}")
    
    elif cmd == "search":
        query = " ".join(sys.argv[2:])
        results = idx.search(query, limit=5)
        for i, r in enumerate(results):
            print(f"\n[{i+1}] {r['title']}")
            print(f"    Source: {r['source_type']} | Category: {r['category']}")
            print(f"    Path: {r['path']}")
            print(f"    Snippet: {r.get('snippet', '')[:100]}...")
    
    elif cmd == "add":
        path = sys.argv[2]
        source_type = sys.argv[3] if len(sys.argv) > 3 else "manual"
        result = idx.add_file(path, source_type)
        print(f"✅ {result}")
    
    elif cmd == "add-dir":
        dir_path = sys.argv[2]
        source_type = sys.argv[3] if len(sys.argv) > 3 else "manual"
        results = idx.add_directory(dir_path, source_type)
        indexed = sum(1 for r in results if r['status'] == 'indexed')
        unchanged = sum(1 for r in results if r['status'] == 'unchanged')
        print(f"✅ Indexed: {indexed}, Unchanged: {unchanged}")
    
    idx.close()
