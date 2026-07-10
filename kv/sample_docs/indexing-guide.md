# Indexing Guide

Add Markdown files with the `index` or `index-dir` command.

The index stores document metadata, full document text, chunk text, and FTS rows. The health command checks that FTS rows still have parent document and chunk rows.

If a file changes, indexing the file again replaces its old chunks.
