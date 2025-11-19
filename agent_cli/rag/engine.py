"""Core RAG Engine Logic (Functional)."""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from agent_cli.rag.models import Message
from agent_cli.rag.retriever import search_context
from agent_cli.rag.store import (
    delete_by_file_path,
    get_all_metadata,
    upsert_docs,
)
from agent_cli.rag.utils import chunk_text, get_file_hash, load_document_text

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    import httpx
    from chromadb import Collection
    from sentence_transformers import CrossEncoder

    from agent_cli.rag.models import ChatRequest

logger = logging.getLogger("agent_cli.rag.engine")


def load_hashes_from_metadata(collection: Collection) -> dict[str, str]:
    """Rebuild hash cache from existing DB."""
    hashes = {}
    try:
        metadatas = get_all_metadata(collection)
        for meta in metadatas:
            if meta and "file_path" in meta and "file_hash" in meta:
                hashes[str(meta["file_path"])] = str(meta["file_hash"])
    except Exception:
        logger.warning("Could not load existing hashes", exc_info=True)
    return hashes


def index_file(
    collection: Collection,
    docs_folder: Path,
    file_path: Path,
    file_hashes: dict[str, str],
) -> None:
    """Index or reindex a single file."""
    if not file_path.exists():
        return

    try:
        # Check if file changed
        current_hash = get_file_hash(file_path)
        relative_path = str(file_path.relative_to(docs_folder))

        if relative_path in file_hashes and file_hashes[relative_path] == current_hash:
            return  # No change, skip

        # Remove old chunks first (atomic-ish update)
        remove_file(collection, docs_folder, file_path, file_hashes)

        # Load document
        text = load_document_text(file_path)
        if not text or not text.strip():
            return  # Unsupported or empty

        # Chunk
        chunks = chunk_text(text)
        if not chunks:
            return

        # Index chunks
        ids = []
        documents = []
        metadatas = []

        timestamp = datetime.datetime.now(datetime.UTC).isoformat()

        for i, chunk in enumerate(chunks):
            doc_id = f"{relative_path}:chunk:{i}"
            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append(
                {
                    "source": file_path.name,
                    "file_path": relative_path,
                    "file_type": file_path.suffix,
                    "chunk_id": i,
                    "total_chunks": len(chunks),
                    "indexed_at": timestamp,
                    "file_hash": current_hash,
                },
            )

        # Upsert to ChromaDB
        upsert_docs(collection, ids, documents, metadatas)

        # Update hash tracking
        file_hashes[relative_path] = current_hash

        logger.info("  ✓ Indexed %s: %d chunks", file_path.name, len(chunks))

    except Exception:
        logger.exception("Failed to index file %s", file_path)


def remove_file(
    collection: Collection,
    docs_folder: Path,
    file_path: Path,
    file_hashes: dict[str, str],
) -> None:
    """Remove all chunks of a file from index."""
    try:
        relative_path = str(file_path.relative_to(docs_folder))
        count = delete_by_file_path(collection, relative_path)
        if count > 0:
            logger.info("  ✓ Removed %d chunks for %s", count, file_path.name)

        # Remove from hash tracking
        file_hashes.pop(relative_path, None)
    except ValueError:
        # Path might not be relative to docs_folder if something weird happened
        pass
    except Exception:
        logger.exception("Error removing file %s", file_path)


def initial_index(
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
) -> None:
    """Index all existing files on startup."""
    logger.info("🔍 Scanning existing files...")
    count = 0
    for file_path in docs_folder.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            try:
                index_file(collection, docs_folder, file_path, file_hashes)
                count += 1
            except Exception:
                logger.exception("Error processing %s", file_path.name)

    logger.info("✅ Initial scan complete. Processed %d files.", count)


async def process_chat_request(
    request: ChatRequest,
    collection: Collection,
    reranker_model: CrossEncoder,
    llama_url: str,
    client: httpx.AsyncClient,
) -> Any:
    """Process a chat request with RAG."""
    # Get last user message
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )

    if not user_message:
        return await _forward_request(request, llama_url, client)

    # Retrieve
    retrieval = search_context(
        collection,
        reranker_model,
        user_message,
        top_k=request.rag_top_k or 3,
    )

    if not retrieval.context:
        # No context found, forward as-is
        return await _forward_request(request, llama_url, client)

    # Augment prompt
    augmented_content = (
        f"Context from documentation:\n{retrieval.context}\n\n---\n\nQuestion: {user_message}"
    )

    # Create new messages list
    augmented_messages = list(request.messages[:-1])
    # Add augmented user message
    augmented_messages.append(Message(role="user", content=augmented_content))

    # Create augmented request
    aug_request = request.model_copy()
    aug_request.messages = augmented_messages

    response = await _forward_request(aug_request, llama_url, client)

    # Add sources to non-streaming response
    if not request.stream and isinstance(response, dict):
        response["rag_sources"] = retrieval.sources

    return response


async def _forward_request(
    request: ChatRequest,
    llama_url: str,
    client: httpx.AsyncClient,
) -> Any:
    """Forward to llama.cpp."""
    # Filter out RAG-specific fields before forwarding
    forward_payload = request.model_dump(exclude={"rag_top_k"})

    if request.stream:

        async def generate() -> AsyncGenerator[str, None]:
            try:
                async with client.stream(
                    "POST",
                    f"{llama_url}/v1/chat/completions",
                    json=forward_payload,
                ) as response:
                    if response.status_code != 200:  # noqa: PLR2004
                        error_text = await response.read()
                        yield f"data: {json.dumps({'error': str(error_text)})}\n\n"
                        return

                    async for chunk in response.aiter_raw():
                        if isinstance(chunk, bytes):
                            yield chunk.decode("utf-8")
                        else:
                            yield chunk
            except Exception as e:
                logger.exception("Streaming error")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    response = await client.post(
        f"{llama_url}/v1/chat/completions",
        json=forward_payload,
    )
    if response.status_code != 200:  # noqa: PLR2004
        logger.error(
            "Upstream error %s: %s",
            response.status_code,
            response.text,
        )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Upstream error: {response.text}",
        )

    return response.json()
