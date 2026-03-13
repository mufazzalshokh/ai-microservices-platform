from __future__ import annotations


def test_chunk_empty_text(chunk_text):
    assert chunk_text("") == []


def test_chunk_short_text(chunk_text):
    assert chunk_text("Hello world", chunk_size=500) == ["Hello world"]


def test_chunk_long_text_produces_multiple_chunks(chunk_text):
    text = "word " * 300
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) > 1


def test_chunks_cover_all_content(chunk_text):
    words = [f"word{i}" for i in range(100)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    combined = " ".join(chunks)
    for word in words:
        assert word in combined, f"{word} missing from chunks"


def test_chunk_overlap_creates_shared_content(chunk_text):
    text = "A" * 100 + " " + "B" * 100 + " " + "C" * 100
    chunks = chunk_text(text, chunk_size=120, overlap=30)
    assert len(chunks) >= 2


def test_extract_utf8_text(extract_text_from_bytes):
    result = extract_text_from_bytes("Hello world".encode("utf-8"), "text/plain")
    assert result == "Hello world"


def test_extract_markdown(extract_text_from_bytes):
    result = extract_text_from_bytes("# Title\n\nSome content".encode("utf-8"), "text/markdown")
    assert "Title" in result


def test_extract_unsupported_type_returns_empty(extract_text_from_bytes):
    result = extract_text_from_bytes(b"\x89PNG\r\n", "image/png")
    assert result == ""
