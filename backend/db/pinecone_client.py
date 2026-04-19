from __future__ import annotations

from pinecone import Pinecone, ServerlessSpec

from backend.config import get_settings

_client: Pinecone | None = None


def get_pinecone() -> Pinecone:
    global _client
    if _client is None:
        settings = get_settings()
        _client = Pinecone(api_key=settings.pinecone_api_key)
    return _client


def get_index() -> object:
    settings = get_settings()
    pc = get_pinecone()
    return pc.Index(settings.pinecone_index)


def ensure_index_exists() -> None:
    """Create the nexus-memory index if it does not yet exist."""
    settings = get_settings()
    pc = get_pinecone()
    existing = [idx["name"] for idx in pc.list_indexes()]
    if settings.pinecone_index not in existing:
        pc.create_index(
            name=settings.pinecone_index,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
