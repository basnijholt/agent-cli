"""RAG data models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    """Chat message model."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat completion request model."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[Message]
    temperature: float | None = 0.7
    max_tokens: int | None = 1000
    stream: bool | None = False
    rag_top_k: int | None = None
    rag_enable_tools: bool | None = True


class DocMetadata(BaseModel):
    """Metadata for an indexed document chunk."""

    source: str
    file_path: str
    file_type: str
    chunk_id: int
    total_chunks: int
    indexed_at: str
    file_hash: str
    file_mtime: float


class RagSource(BaseModel):
    """Source information for RAG response."""

    source: str
    path: str
    chunk_id: int
    score: float


class RetrievalResult(BaseModel):
    """Result of a RAG retrieval operation."""

    context: str
    sources: list[RagSource]
