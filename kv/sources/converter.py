#!/usr/bin/env python3
"""
KV Source Converter — multi-format → Markdown pipeline

Converts documents to clean Markdown for the Knowledge Vault using xberg
(107+ formats: PDF, EPUB, DOCX, PPTX, HTML, spreadsheets, and more).
Plain text/markdown files are copied directly without xberg.

xberg is an optional dependency (lazy import), consistent with the
original pdfplumber/ebooklib approach: it is only required for
non-text formats.

Usage:
  from kv.sources.converter import Converter
  conv = Converter()
  md_path = conv.convert("input.pdf", output_dir="kv/obsidian")
"""

import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent.parent / "obsidian"

# File types read directly as text (no xberg needed)
TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".text", ".log"}


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

        if suffix in TEXT_EXTENSIONS:
            return self._convert_text(input_path, output_dir, source_type)

        return self._convert_with_xberg(input_path, output_dir, source_type)

    def _convert_with_xberg(self, input_path: Path, output_dir: str,
                            source_type: str) -> dict:
        """Convert any xberg-supported document format to Markdown"""
        try:
            import xberg
            from xberg import ExtractInput, ExtractionConfig
        except ImportError:
            return {"status": "error",
                    "error": "xberg not installed. Run: pip install xberg"}

        try:
            result = asyncio.run(
                xberg.extract(ExtractInput(uri=str(input_path)),
                              ExtractionConfig(use_cache=False)))
        except Exception as e:
            return {"status": "error", "error": f"xberg extraction failed: {e}"}

        if not result.results:
            err = result.errors[0] if result.errors else "no output produced"
            return {"status": "error", "error": f"xberg produced no document: {err}"}

        content = self._clean_text(result.results[0].content or "")
        if not content:
            return {"status": "error", "error": "xberg produced empty content"}

        format_type = input_path.suffix.lstrip(".").lower() or "unknown"
        return self._save_markdown(content, input_path, output_dir, source_type, format_type)

    def _convert_text(self, input_path: Path, output_dir: str, source_type: str):
        """Convert plain text or markdown (just copy/clean)"""
        try:
            content = input_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return {"status": "error", "error": f"Could not read file: {e}"}

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
