"""Ingestion logic for memory (LLM Extraction, Reconciliation, Summarization)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx

from agent_cli.memory._git import commit_changes
from agent_cli.memory._persistence import (
    delete_memory_files,
    persist_entries,
    persist_hierarchical_summary,
)
from agent_cli.memory._prompt import (
    FACT_INSTRUCTIONS,
    FACT_SYSTEM_PROMPT,
    UPDATE_MEMORY_PROMPT,
)
from agent_cli.memory._retrieval import gather_relevant_existing_memories
from agent_cli.memory._store import delete_entries, get_final_summary
from agent_cli.memory.entities import Fact
from agent_cli.memory.models import (
    MemoryAdd,
    MemoryDecision,
    MemoryDelete,
    MemoryIgnore,
    MemoryUpdate,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

    from agent_cli.summarizer import SummaryResult

LOGGER = logging.getLogger(__name__)


def _elapsed_ms(start: float) -> float:
    """Return elapsed milliseconds since start."""
    return (perf_counter() - start) * 1000


async def extract_salient_facts(
    *,
    user_message: str | None,
    assistant_message: str | None,
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> list[str]:
    """Run an LLM agent to extract facts from the transcript."""
    if not user_message and not assistant_message:
        return []

    from pydantic_ai import Agent  # noqa: PLC0415
    from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIChatModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

    # Extract facts from the latest user turn only (ignore assistant/system).
    transcript = user_message or ""
    LOGGER.info("Extracting facts from transcript: %r", transcript)

    provider = OpenAIProvider(api_key=api_key or "dummy", base_url=openai_base_url)
    model_cfg = OpenAIChatModel(model_name=model, provider=provider)
    agent = Agent(
        model=model_cfg,
        system_prompt=FACT_SYSTEM_PROMPT,
        output_type=list[str],
        retries=2,
    )
    instructions = FACT_INSTRUCTIONS

    try:
        facts = await agent.run(transcript, instructions=instructions)
        LOGGER.info("Raw fact extraction output: %s", facts.output)
        return facts.output
    except (httpx.HTTPError, AgentRunError, UnexpectedModelBehavior):
        LOGGER.warning("PydanticAI fact extraction transient failure", exc_info=True)
        return []
    except Exception:
        LOGGER.exception("PydanticAI fact extraction internal error")
        raise


def process_reconciliation_decisions(
    decisions: list[MemoryDecision],
    id_map: dict[int, str],
    conversation_id: str,
    source_id: str,
    created_at: datetime,
) -> tuple[list[Fact], list[str], dict[str, str]]:
    """Process LLM decisions into actionable changes."""
    to_add: list[Fact] = []
    to_delete: list[str] = []
    replacement_map: dict[str, str] = {}

    LOGGER.info(
        "Reconcile decisions raw: %s",
        [d.model_dump() for d in decisions],
    )

    for dec in decisions:
        if isinstance(dec, MemoryAdd):
            text = dec.text.strip()
            if text:
                to_add.append(
                    Fact(
                        id=str(uuid4()),
                        conversation_id=conversation_id,
                        content=text,
                        source_id=source_id,
                        created_at=created_at,
                    ),
                )
        elif isinstance(dec, MemoryUpdate):
            orig = id_map.get(dec.id)
            text = dec.text.strip()
            if text:
                if orig:
                    # Update existing memory: delete old, add new
                    new_id = str(uuid4())
                    to_delete.append(orig)
                    to_add.append(
                        Fact(
                            id=new_id,
                            conversation_id=conversation_id,
                            content=text,
                            source_id=source_id,
                            created_at=created_at,
                        ),
                    )
                    replacement_map[orig] = new_id
                else:
                    # UPDATE with unknown ID = treat as ADD (model used wrong event)
                    to_add.append(
                        Fact(
                            id=str(uuid4()),
                            conversation_id=conversation_id,
                            content=text,
                            source_id=source_id,
                            created_at=created_at,
                        ),
                    )
        elif isinstance(dec, MemoryDelete):
            orig = id_map.get(dec.id)
            if orig:
                to_delete.append(orig)
        elif isinstance(dec, MemoryIgnore):
            pass  # NONE ignored
    return to_add, to_delete, replacement_map


async def reconcile_facts(
    collection: Collection,
    conversation_id: str,
    new_facts: list[str],
    source_id: str,
    created_at: datetime,
    *,
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> tuple[list[Fact], list[str], dict[str, str]]:
    """Use an LLM to decide add/update/delete/none for facts, with id remapping."""
    if not new_facts:
        return [], [], {}

    existing = gather_relevant_existing_memories(collection, conversation_id, new_facts)
    LOGGER.info("Reconcile: Found %d existing memories for new facts %s", len(existing), new_facts)
    if not existing:
        LOGGER.info("Reconcile: no existing memory facts; defaulting to add all new facts")
        entries = [
            Fact(
                id=str(uuid4()),
                conversation_id=conversation_id,
                content=f,
                source_id=source_id,
                created_at=created_at,
            )
            for f in new_facts
            if f.strip()
        ]
        return entries, [], {}
    id_map: dict[int, str] = {idx: mem.id for idx, mem in enumerate(existing)}
    existing_json = [{"id": idx, "text": mem.content} for idx, mem in enumerate(existing)]
    existing_ids = set(id_map.keys())

    from pydantic_ai import Agent, ModelRetry, PromptedOutput  # noqa: PLC0415
    from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIChatModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415
    from pydantic_ai.settings import ModelSettings  # noqa: PLC0415

    provider = OpenAIProvider(api_key=api_key or "dummy", base_url=openai_base_url)
    model_cfg = OpenAIChatModel(
        model_name=model,
        provider=provider,
        settings=ModelSettings(temperature=0.0, max_tokens=512),
    )
    agent = Agent(
        model=model_cfg,
        system_prompt=UPDATE_MEMORY_PROMPT,
        output_type=PromptedOutput(list[MemoryDecision]),  # JSON mode instead of tool calls
        retries=3,
    )

    @agent.output_validator
    def validate_decisions(decisions: list[MemoryDecision]) -> list[MemoryDecision]:
        """Validate LLM decisions and provide feedback for retry."""
        errors = []
        for dec in decisions:
            if (
                isinstance(dec, (MemoryUpdate, MemoryDelete, MemoryIgnore))
                and dec.id not in existing_ids
            ):
                if isinstance(dec, MemoryUpdate):
                    errors.append(
                        f"UPDATE with id={dec.id} is invalid: that ID doesn't exist. "
                        f"Valid existing IDs are: {sorted(existing_ids)}. "
                        f"For NEW facts, use ADD with a new ID.",
                    )
                elif isinstance(dec, MemoryDelete):
                    errors.append(f"DELETE with id={dec.id} is invalid: that ID doesn't exist.")
                else:  # MemoryIgnore (NONE)
                    errors.append(f"NONE with id={dec.id} is invalid: that ID doesn't exist.")
        if errors:
            msg = "Invalid memory decisions:\n" + "\n".join(f"- {e}" for e in errors)
            raise ModelRetry(msg)
        return decisions

    # Format with separate sections for existing and new facts
    existing_str = json.dumps(existing_json, ensure_ascii=False, indent=2)
    new_facts_str = json.dumps(new_facts, ensure_ascii=False, indent=2)
    payload = f"""Current memory:
```
{existing_str}
```

New facts to process:
```
{new_facts_str}
```"""
    LOGGER.info("Reconcile payload: %s", payload)
    try:
        result = await agent.run(payload)
        decisions = result.output
    except (httpx.HTTPError, AgentRunError, UnexpectedModelBehavior):
        LOGGER.warning(
            "Update memory agent transient failure; defaulting to add all new facts",
            exc_info=True,
        )
        entries = [
            Fact(
                id=str(uuid4()),
                conversation_id=conversation_id,
                content=f,
                source_id=source_id,
                created_at=created_at,
            )
            for f in new_facts
            if f.strip()
        ]
        return entries, [], {}
    except Exception:
        LOGGER.exception("Update memory agent internal error")
        raise

    to_add, to_delete, replacement_map = process_reconciliation_decisions(
        decisions,
        id_map,
        conversation_id=conversation_id,
        source_id=source_id,
        created_at=created_at,
    )

    LOGGER.info(
        "Reconcile decisions: add=%d, delete=%d, events=%s",
        len(to_add),
        len(to_delete),
        [dec.event for dec in decisions],
    )
    return to_add, to_delete, replacement_map


async def summarize_content(
    *,
    content: str,
    prior_summary: str | None = None,
    content_type: str = "general",
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> SummaryResult:
    """Adaptively summarize content based on its length.

    Automatically selects the appropriate summarization strategy
    (NONE, BRIEF, STANDARD, DETAILED, HIERARCHICAL) based on input token count.

    Args:
        content: The content to summarize.
        prior_summary: Optional prior summary for context continuity.
        content_type: Type of content ("general", "conversation", "journal", "document").
        openai_base_url: Base URL for OpenAI-compatible API.
        api_key: API key for the LLM.
        model: Model name to use for summarization.

    Returns:
        SummaryResult with the summary and metadata.

    """
    # Import here to avoid circular imports and allow optional dependency
    from agent_cli.summarizer import SummarizerConfig, summarize  # noqa: PLC0415

    config = SummarizerConfig(
        openai_base_url=openai_base_url,
        model=model,
        api_key=api_key,
    )
    return await summarize(
        content=content,
        config=config,
        prior_summary=prior_summary,
        content_type=content_type,
    )


async def store_adaptive_summary(
    collection: Collection,
    memory_root: Path,
    conversation_id: str,
    summary_result: SummaryResult,
) -> list[str]:
    """Store an adaptive summary result to files and ChromaDB.

    This stores all levels of a hierarchical summary (L1, L2, L3) or
    just the final summary for simpler levels. Old summaries are deleted first.

    Files are stored as Markdown with YAML front matter in a hierarchical structure:
    - summaries/L1/chunk_{n}.md - L1 chunk summaries
    - summaries/L2/group_{n}.md - L2 group summaries
    - summaries/L3/final.md - L3 final summary

    Args:
        collection: ChromaDB collection.
        memory_root: Root path for memory files.
        conversation_id: The conversation this summary belongs to.
        summary_result: The result from AdaptiveSummarizer.summarize().

    Returns:
        List of IDs that were stored.

    """
    return persist_hierarchical_summary(
        collection,
        memory_root=memory_root,
        conversation_id=conversation_id,
        summary_result=summary_result,
    )


async def extract_and_store_facts_and_summaries(
    *,
    collection: Collection,
    memory_root: Path,
    conversation_id: str,
    user_message: str | None,
    assistant_message: str | None,
    openai_base_url: str,
    api_key: str | None,
    model: str,
    enable_git_versioning: bool = False,
    source_id: str | None = None,
    enable_summarization: bool = True,
) -> None:
    """Run fact extraction and summary updates, persisting results."""
    fact_start = perf_counter()
    effective_source_id = source_id or str(uuid4())
    fact_created_at = datetime.now(UTC)

    facts = await extract_salient_facts(
        user_message=user_message,
        assistant_message=assistant_message,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
    )
    LOGGER.info(
        "Fact extraction produced %d facts in %.1f ms (conversation=%s)",
        len(facts),
        _elapsed_ms(fact_start),
        conversation_id,
    )
    to_add, to_delete, replacement_map = await reconcile_facts(
        collection,
        conversation_id,
        facts,
        source_id=effective_source_id,
        created_at=fact_created_at,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
    )

    if to_delete:
        delete_entries(collection, ids=list(to_delete))
        delete_memory_files(
            memory_root,
            conversation_id,
            list(to_delete),
            replacement_map=replacement_map,
        )

    if to_add:
        persist_entries(
            collection,
            memory_root=memory_root,
            conversation_id=conversation_id,
            entries=list(to_add),
        )

    # Summarize raw conversation turns (not extracted facts)
    has_content = user_message or assistant_message
    if enable_summarization and has_content:
        prior_summary_entry = get_final_summary(collection, conversation_id)
        prior_summary = prior_summary_entry.content if prior_summary_entry else None

        # Build conversation transcript
        parts = []
        if user_message:
            parts.append(f"User: {user_message}")
        if assistant_message:
            parts.append(f"Assistant: {assistant_message}")
        content_to_summarize = "\n".join(parts)

        summary_start = perf_counter()
        summary_result = await summarize_content(
            content=content_to_summarize,
            prior_summary=prior_summary,
            content_type="conversation",
            openai_base_url=openai_base_url,
            api_key=api_key,
            model=model,
        )
        LOGGER.info(
            "Summary update completed in %.1f ms (conversation=%s, level=%s)",
            _elapsed_ms(summary_start),
            conversation_id,
            summary_result.level.name,
        )
        if summary_result.summary:
            await store_adaptive_summary(
                collection,
                memory_root=memory_root,
                conversation_id=conversation_id,
                summary_result=summary_result,
            )

    if enable_git_versioning:
        await commit_changes(memory_root, f"Add facts to conversation {conversation_id}")
