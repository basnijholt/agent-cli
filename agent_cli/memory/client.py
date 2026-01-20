"""High-level client for interacting with the memory system."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Self

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL, DEFAULT_OPENAI_MODEL
from agent_cli.core.reranker import get_reranker_model
from agent_cli.memory._files import ensure_store_dirs
from agent_cli.memory._git import init_repo
from agent_cli.memory._indexer import MemoryIndex, initial_index, watch_memory_store
from agent_cli.memory._ingest import extract_and_store_facts_and_summaries
from agent_cli.memory._persistence import evict_if_needed
from agent_cli.memory._retrieval import augment_chat_request
from agent_cli.memory._store import init_memory_collection, list_conversation_entries
from agent_cli.memory.engine import process_chat_request
from agent_cli.memory.models import ChatRequest, MemoryRetrieval, Message

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

    from agent_cli.core.reranker import OnnxCrossEncoder


logger = logging.getLogger("agent_cli.memory.client")


class MemoryClient:
    """A client for interacting with the memory system (add, search, chat).

    This class decouples the memory logic from the HTTP server, allowing
    direct usage in other applications or scripts.
    """

    def __init__(
        self,
        memory_path: Path,
        openai_base_url: str,
        embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        embedding_api_key: str | None = None,
        chat_api_key: str | None = None,
        enable_summarization: bool = True,
        default_top_k: int = 5,
        max_entries: int = 500,
        mmr_lambda: float = 0.7,
        recency_weight: float = 0.2,
        score_threshold: float | None = None,
        start_watcher: bool = False,
        enable_git_versioning: bool = True,
    ) -> None:
        """Initialize the memory client."""
        self.memory_path = memory_path.resolve()
        self.openai_base_url = openai_base_url.rstrip("/")
        self.chat_api_key = chat_api_key
        self.enable_summarization = enable_summarization
        self.default_top_k = default_top_k
        self.max_entries = max_entries
        self.mmr_lambda = mmr_lambda
        self.recency_weight = recency_weight
        self.score_threshold = score_threshold
        self.enable_git_versioning = enable_git_versioning

        _, snapshot_path = ensure_store_dirs(self.memory_path)

        if self.enable_git_versioning:
            init_repo(self.memory_path)

        logger.info("Initializing memory collection...")
        self.collection: Collection = init_memory_collection(
            self.memory_path,
            embedding_model=embedding_model,
            openai_base_url=self.openai_base_url,
            openai_api_key=embedding_api_key,
        )

        self.index = MemoryIndex.from_snapshot(snapshot_path)
        initial_index(self.collection, self.memory_path, index=self.index)

        logger.info("Loading reranker model...")
        self.reranker_model: OnnxCrossEncoder = get_reranker_model()

        self._watch_task: asyncio.Task | None = None
        if start_watcher:
            self.start()

    def start(self) -> None:
        """Start the background file watcher."""
        if self._watch_task is None:
            self._watch_task = asyncio.create_task(
                watch_memory_store(self.collection, self.memory_path, index=self.index),
            )

    async def stop(self) -> None:
        """Stop the background file watcher."""
        if self._watch_task:
            self._watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None

    async def __aenter__(self) -> Self:
        """Start the client context."""
        self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Stop the client context."""
        await self.stop()

    async def add(
        self,
        text: str,
        conversation_id: str = "default",
        model: str = DEFAULT_OPENAI_MODEL,
    ) -> None:
        """Add a memory by extracting facts from text and reconciling them.

        This mimics the 'mem0.add' behavior but uses our advanced reconciliation
        pipeline (Add/Update/Delete) and updates the conversation summary.
        """
        await extract_and_store_facts_and_summaries(
            collection=self.collection,
            memory_root=self.memory_path,
            conversation_id=conversation_id,
            user_message=text,
            assistant_message=None,
            openai_base_url=self.openai_base_url,
            api_key=self.chat_api_key,
            model=model,
            enable_git_versioning=self.enable_git_versioning,
            enable_summarization=self.enable_summarization,
        )
        evict_if_needed(self.collection, self.memory_path, conversation_id, self.max_entries)

    async def search(
        self,
        query: str,
        conversation_id: str = "default",
        top_k: int | None = None,
        model: str = DEFAULT_OPENAI_MODEL,
        recency_weight: float | None = None,
        score_threshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> MemoryRetrieval:
        """Search for memories relevant to a query.

        Args:
            query: The search query text.
            conversation_id: Conversation scope for the search.
            top_k: Number of results to return.
            model: Model for any LLM operations.
            recency_weight: Weight for recency scoring (0-1).
            score_threshold: Minimum relevance score threshold.
            filters: Optional metadata filters. Examples:
                - {"role": "user"} - exact match
                - {"created_at": {"gte": "2024-01-01"}} - comparison
                - {"$or": [{"role": "user"}, {"role": "assistant"}]} - logical OR
                Operators: eq, ne, gt, gte, lt, lte, in, nin

        """
        dummy_request = ChatRequest(
            messages=[Message(role="user", content=query)],
            model=model,
            memory_id=conversation_id,
            memory_top_k=top_k or self.default_top_k,
        )

        _, retrieval, _, _ = await augment_chat_request(
            dummy_request,
            self.collection,
            reranker_model=self.reranker_model,
            default_top_k=top_k or self.default_top_k,
            include_global=True,
            mmr_lambda=self.mmr_lambda,
            recency_weight=recency_weight if recency_weight is not None else self.recency_weight,
            score_threshold=score_threshold
            if score_threshold is not None
            else self.score_threshold,
            filters=filters,
        )
        return retrieval or MemoryRetrieval(entries=[])

    def list_all(
        self,
        conversation_id: str = "default",
        include_summary: bool = False,
    ) -> list[dict[str, Any]]:
        """List all stored memories for a conversation.

        Args:
            conversation_id: Conversation scope.
            include_summary: Whether to include summary entries.

        Returns:
            List of memory entries with id, content, and metadata.

        """
        entries = list_conversation_entries(
            self.collection,
            conversation_id,
            include_summary=include_summary,
        )
        return [
            {
                "id": e.id,
                "content": e.content,
                "role": e.metadata.role,
                "created_at": e.metadata.created_at,
            }
            for e in entries
        ]

    async def chat(
        self,
        messages: list[dict[str, str]] | list[Any],
        conversation_id: str = "default",
        model: str = DEFAULT_OPENAI_MODEL,
        stream: bool = False,
        api_key: str | None = None,
        memory_top_k: int | None = None,
        recency_weight: float | None = None,
        score_threshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Any:
        """Process a chat request (Augment -> LLM -> Update Memory).

        Args:
            messages: Chat messages.
            conversation_id: Conversation scope.
            model: LLM model to use.
            stream: Whether to stream the response.
            api_key: Optional API key override.
            memory_top_k: Number of memories to retrieve.
            recency_weight: Weight for recency scoring (0-1).
            score_threshold: Minimum relevance score threshold.
            filters: Optional metadata filters for memory retrieval.

        """
        req = ChatRequest(
            messages=messages,  # type: ignore[arg-type]
            model=model,
            memory_id=conversation_id,
            stream=stream,
            memory_top_k=memory_top_k if memory_top_k is not None else self.default_top_k,
            memory_recency_weight=recency_weight,
            memory_score_threshold=score_threshold,
        )

        return await process_chat_request(
            req,
            collection=self.collection,
            memory_root=self.memory_path,
            openai_base_url=self.openai_base_url,
            reranker_model=self.reranker_model,
            default_top_k=self.default_top_k,
            api_key=api_key or self.chat_api_key,
            enable_summarization=self.enable_summarization,
            max_entries=self.max_entries,
            mmr_lambda=self.mmr_lambda,
            recency_weight=recency_weight if recency_weight is not None else self.recency_weight,
            score_threshold=score_threshold
            if score_threshold is not None
            else self.score_threshold,
            postprocess_in_background=True,
            enable_git_versioning=self.enable_git_versioning,
            filters=filters,
        )
