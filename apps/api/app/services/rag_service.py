"""Shared deterministic text splitting for the database-backed RAG service.

The previous module also exposed an in-process JSON-file vector store.  That
store was not the source used by the RAG management API, was not safe across
multiple workers, and could silently diverge after restart.  Production RAG
documents and embeddings now have one authoritative path: ``rag_document`` and
``rag_chunk`` through :mod:`app.api.v1.routes.rag`.
"""

from __future__ import annotations


CHUNK_SIZE = 500
CHUNK_OVERLAP = 80


def split_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split bounded text by paragraphs with deterministic character overlap."""
    try:
        normalized_chunk_size = int(chunk_size)
        normalized_overlap = int(overlap)
    except (TypeError, ValueError) as exc:
        raise ValueError("chunk_size and overlap must be integers") from exc
    if normalized_chunk_size < 50 or normalized_chunk_size > 20_000:
        raise ValueError("chunk_size must be between 50 and 20000")
    if normalized_overlap < 0 or normalized_overlap >= normalized_chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    value = str(text or "").replace("\x00", "").strip()
    if not value:
        return []
    if len(value) <= normalized_chunk_size:
        return [value]

    chunks: list[str] = []
    current = ""
    step = normalized_chunk_size - normalized_overlap
    for paragraph in value.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) > normalized_chunk_size:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), step):
                chunk = paragraph[start : start + normalized_chunk_size]
                if chunk:
                    chunks.append(chunk)
                if start + normalized_chunk_size >= len(paragraph):
                    break
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= normalized_chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
        prefix = chunks[-1][-normalized_overlap:] if normalized_overlap and chunks else ""
        current = f"{prefix}\n\n{paragraph}" if prefix else paragraph
        # A large overlap plus paragraph can exceed the target.  Preserve the
        # paragraph and cap only the repeated prefix.
        if len(current) > normalized_chunk_size:
            prefix_room = max(normalized_chunk_size - len(paragraph) - 2, 0)
            prefix = prefix[-prefix_room:] if prefix_room else ""
            current = f"{prefix}\n\n{paragraph}" if prefix else paragraph

    if current:
        chunks.append(current)
    return chunks


__all__ = ["CHUNK_OVERLAP", "CHUNK_SIZE", "split_text"]
