#!/usr/bin/env python3
"""
KV Source Converter — PDF/EPUB → Markdown pipeline

Converts various document formats to clean Markdown for the Knowledge Vault.
Handles: PDF, EPUB, plain text, HTML

Usage:
  from kv.sources.converter import Converter
  conv = Converter()
  md_path = conv.convert("input.pdf", output_dir="kv/obsidian")
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent.parent / "obsidian"


class Converter:
    """Convert documents to clean Markdown"""
    
    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir or OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def convert(self, input_path: str, output_dir: str = None, 
                source_type: str = "manual") -> dict:
        """
        Convert a file to Markdown.
        
        Returns dict with status, output_path, etc.
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            return {"status": "error", "error": f"File not found: {input_path}"}
        
        # Detect format
        suffix = input_path.suffix.lower()
        
        if suffix == ".pdf":
            return self._convert_pdf(input_path, output_dir, source_type)
        elif suffix == ".epub":
            return self._convert_epub(input_path, output_dir, source_type)
        elif suffix == ".html" or suffix == ".htm":
            return self._convert_html(input_path, output_dir, source_type)
        elif suffix == ".txt" or suffix == ".md":
            return self._convert_text(input_path, output_dir, source_type)
        else:
            return {"status": "error", "error": f"Unsupported format: {suffix}"}
    
    def _convert_pdf(self, input_path: Path, output_dir: str, source_type: str) -> dict:
        """Convert PDF to Markdown"""
        try:
            import pdfplumber
            
            content = []
            with pdfplumber.open(str(input_path)) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        # Clean PDF artifacts
                        text = self._clean_text(text)
                        content.append(f"<!-- Page {i+1} -->\n{text}")
            
            md_content = "\n\n".join(content)
            return self._save_markdown(md_content, input_path, output_dir, source_type, "pdf")
            
        except ImportError:
            return {"status": "error", "error": "pdfplumber not installed. Run: pip install pdfplumber"}
    
    def _convert_epub(self, input_path: Path, output_dir: str, source_type: str) -> dict:
        """Convert EPUB to Markdown"""
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
            
            book = epub.read_epub(str(input_path))
            content = []
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text = soup.get_text()
                    text = self._clean_text(text)
                    if text.strip():
                        content.append(text)
            
            md_content = "\n\n".join(content)
            return self._save_markdown(md_content, input_path, output_dir, source_type, "epub")
            
        except ImportError:
            return {"status": "error", "error": "ebooklib/bs4 not installed. Run: pip install ebooklib beautifulsoup4"}
    
    def _convert_html(self, input_path: Path, output_dir: str, source_type: str) -> dict:
        """Convert HTML to Markdown"""
        try:
            from bs4 import BeautifulSoup
            
            with open(input_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for element in soup(["script", "style"]):
                element.decompose()
            
            text = soup.get_text()
            text = self._clean_text(text)
            
            return self._save_markdown(text, input_path, output_dir, source_type, "html")
            
        except ImportError:
            return {"status": "error", "error": "bs4 not installed. Run: pip install beautifulsoup4"}
    
    def _convert_text(self, input_path: Path, output_dir: str, source_type: str) -> dict:
        """Convert plain text or markdown (just copy/clean)"""
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = self._clean_text(content)
        return self._save_markdown(content, input_path, output_dir, source_type, "text")
    
    def _clean_text(self, text: str) -> str:
        """Clean text artifacts"""
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        # Remove common PDF artifacts
        text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)  # Hyphenation
        text = re.sub(r'\n\d+\n', '\n', text)  # Page numbers
        text = re.sub(r'(?m)^\d+\s*$', '', text)  # Standalone numbers
        
        return text.strip()
    
    def _save_markdown(self, content: str, input_path: Path, 
                       output_dir: str, source_type: str, format_type: str) -> dict:
        """Save converted content as Markdown"""
        # Create output directory
        out_dir = Path(output_dir) if output_dir else self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        stem = input_path.stem
        # Clean filename
        stem = re.sub(r'[^a-zA-Z0-9_-]', '_', stem)
        stem = re.sub(r'_+', '_', stem).strip('_')
        
        output_path = out_dir / f"{stem}.md"
        
        # Add frontmatter
        frontmatter = f"""---
title: "{input_path.stem}"
source_type: "{source_type}"
format: "{format_type}"
converted_at: "{datetime.now().isoformat()}"
original_filename: "{input_path.name}"
---

"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter + content)
        
        return {
            "status": "converted",
            "input": str(input_path),
            "output": str(output_path),
            "format": format_type,
            "source_type": source_type,
            "size": len(content)
        }
    
    def convert_batch(self, input_paths: list, output_dir: str = None,
                      source_type: str = "manual") -> list:
        """Convert multiple files"""
        results = []
        for path in input_paths:
            result = self.convert(path, output_dir, source_type)
            results.append(result)
        return results


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python converter.py <input> [--source-type=TYPE] [--output-dir=DIR]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    source_type = "manual"
    output_dir = None
    
    for arg in sys.argv[2:]:
        if arg.startswith("--source-type="):
            source_type = arg.split("=")[1]
        elif arg.startswith("--output-dir="):
            output_dir = arg.split("=")[1]
    
    conv = Converter(output_dir)
    result = conv.convert(input_path, source_type=source_type)
    
    print(f"📄 Conversion Result:")
    for k, v in result.items():
        print(f"   {k}: {v}")
