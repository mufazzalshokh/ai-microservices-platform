from __future__ import annotations

from shared.logging import get_logger

logger = get_logger(__name__)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """
    Split text into overlapping chunks.

    Why overlapping? So that sentences spanning a chunk boundary
    aren't cut off - both chunks share context around the boundary.

    Example with chunk_size=20, overlap=5:
      text = "AAAAABBBBBCCCCCDDDDDEEEEE"
      chunks = ["AAAAABBBBBCCCCC", "CCCCCDDDDDEEEEE"]
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:])
            break

        boundary = _find_boundary(text, end)

        # Guard: boundary must always be ahead of start to prevent infinite loop
        if boundary <= start:
            boundary = end

        chunks.append(text[start:boundary])

        next_start = boundary - overlap
        # Guard: next_start must always advance forward
        if next_start <= start:
            next_start = start + 1

        start = next_start

    result = [c.strip() for c in chunks if c.strip()]
    logger.debug(
        "text_chunked",
        total_chars=len(text),
        num_chunks=len(result),
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return result


def _find_boundary(text: str, pos: int) -> int:
    """
    Look backward from pos to find a good split point.
    Prefers sentence endings, then word boundaries.
    """
    search_start = max(0, pos - 100)
    segment = text[search_start:pos]

    for i in reversed(range(len(segment))):
        if segment[i] in ".!?":
            return search_start + i + 1

    for i in reversed(range(len(segment))):
        if segment[i] in " \n\t":
            return search_start + i + 1

    return pos


def extract_text_from_bytes(content: bytes, content_type: str) -> str:
    """
    Extract plain text from uploaded file bytes.
    Supports: plain text, markdown, CSV, JSON.
    """
    text_types = {
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
    }

    if content_type in text_types or content_type.startswith("text/"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace")

    logger.warning("unsupported_content_type", content_type=content_type)
    return ""
