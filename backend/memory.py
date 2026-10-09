"""Small Chroma-backed memory store for shared markdown knowledge."""
import hashlib
import os
import re
from pathlib import Path

_CHUNK_SIZE = 1200
_OVERLAP = 150
_collection = None
_fallback: dict[str, list[dict[str, str]]] = {}


def _chunks(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - _OVERLAP
    return chunks


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        path = os.getenv("MEMORY_DB_PATH", str(Path(__file__).resolve().parent / ".memory"))
        client = chromadb.PersistentClient(path=path)
        _collection = client.get_or_create_collection("workspace_memory")
    return _collection


def index(file: str, text: str):
    """Replace the indexed chunks for one markdown file."""
    chunks = _chunks(text)
    _fallback[file] = [{"text": chunk, "file": file} for chunk in chunks]
    try:
        collection = _get_collection()
        collection.delete(where={"file": file})
        if chunks:
            collection.add(
                ids=[hashlib.sha1(f"{file}:{i}:{chunk}".encode()).hexdigest() for i, chunk in enumerate(chunks)],
                documents=chunks,
                metadatas=[{"file": file} for _ in chunks],
            )
    except Exception:
        # Offline mock mode still gets deterministic lexical retrieval below.
        return


def search(query: str, k: int = 3, file: str | None = None) -> list[dict[str, str]]:
    """Return the most relevant memory chunks, optionally limited to one file."""
    try:
        collection = _get_collection()
        result = collection.query(
            query_texts=[query],
            n_results=k,
            where={"file": file} if file else None,
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        return [
            {"text": document, "file": (metadata or {}).get("file", file or "")}
            for document, metadata in zip(documents, metadatas)
        ]
    except Exception:
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        candidates = [item for name, items in _fallback.items() if not file or name == file for item in items]
        ranked = sorted(
            candidates,
            key=lambda item: sum(term in item["text"].lower() for term in terms),
            reverse=True,
        )
        return ranked[:k]
