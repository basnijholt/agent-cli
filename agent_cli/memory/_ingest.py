"""Ingestion logic for memory (LLM Extraction, Reconciliation, Summarization)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from agent_cli.memory._git import commit_changes
from agent_cli.memory._persistence import (
    delete_memory_files,
    persist_entries,
    persist_summary,
)
from agent_cli.memory._prompt import (
    FACT_INSTRUCTIONS,
    FACT_SYSTEM_PROMPT,
    SUMMARY_PROMPT,
    UPDATE_MEMORY_PROMPT,
)
from agent_cli.memory._retrieval import gather_relevant_existing_memories
from agent_cli.memory._store import delete_entries, get_summary_entry
from agent_cli.memory.entities import Fact, Summary
from agent_cli.memory.models import MemoryDecision, SummaryOutput

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

logger = logging.getLogger("agent_cli.memory.ingest")

_SUMMARY_ROLE = "summary"


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

    # Extract facts from the latest user turn only (ignore assistant/system).
    transcript = user_message or ""
    logger.info("Extracting facts from transcript: %r", transcript)

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
        logger.info("Raw fact extraction output: %s", facts.output)
        return facts.output
    except (httpx.HTTPError, AgentRunError, UnexpectedModelBehavior):
        logger.warning("PydanticAI fact extraction transient failure", exc_info=True)
        return []
    except Exception:
        logger.exception("PydanticAI fact extraction internal error")
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

    logger.info(
        "Reconcile decisions raw: %s",
        [d.model_dump() for d in decisions],
    )

    for dec in decisions:
        if dec.event == "ADD" and dec.text:
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
        elif dec.event == "UPDATE" and dec.id is not None and dec.text:
            orig = id_map.get(dec.id)
            if orig:
                text = dec.text.strip()
                if text:
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
        elif dec.event == "DELETE" and dec.id is not None:
            orig = id_map.get(dec.id)
            if orig:
                to_delete.append(orig)
        # NONE ignored
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
    logger.info("Reconcile: Found %d existing memories for new facts %s", len(existing), new_facts)
    if not existing:
        logger.info("Reconcile: no existing memory facts; defaulting to add all new facts")
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
    existing_json = [{"id": str(idx), "text": mem.content} for idx, mem in enumerate(existing)]

    provider = OpenAIProvider(api_key=api_key or "dummy", base_url=openai_base_url)
    model_cfg = OpenAIChatModel(
        model_name=model,
        provider=provider,
        settings=ModelSettings(temperature=0.0, max_tokens=512),
    )
    agent = Agent(
        model=model_cfg,
        system_prompt=UPDATE_MEMORY_PROMPT,
        output_type=list[MemoryDecision],
        retries=3,
    )

    payload_obj = {"existing": existing_json, "new_facts": new_facts}
    payload = json.dumps(payload_obj, ensure_ascii=False, indent=2)
    logger.info("Reconcile payload JSON: %s", payload)
    try:
        result = await agent.run(payload)
        decisions = result.output or []
    except (httpx.HTTPError, AgentRunError, UnexpectedModelBehavior):
        logger.warning(
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
        logger.exception("Update memory agent internal error")
        raise

    to_add, to_delete, replacement_map = process_reconciliation_decisions(
        decisions,
        id_map,
        conversation_id=conversation_id,
        source_id=source_id,
        created_at=created_at,
    )

    # Safeguard: if the model produced no additions and the new facts would otherwise be lost,
    # retain the new facts. This prevents ending up with an empty fact set after deletes.
    # We trust the LLM if it explicitly decided to KEEP (NONE) or ADD/UPDATE content.
    # We only override if it returned nothing or only DELETEs (which implies replacement failure).
    has_keep_action = any(d.event in ("ADD", "UPDATE", "NONE") for d in decisions)

    if not has_keep_action and new_facts:
        logger.info(
            "Reconcile produced no additions/keeps; retaining new facts to avoid empty store",
        )
        to_add = [
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

    logger.info(
        "Reconcile decisions: add=%d, delete=%d, events=%s",
        len(to_add),
        len(to_delete),
        [dec.event for dec in decisions],
    )
    return to_add, to_delete, replacement_map


async def update_summary(
    *,
    prior_summary: str | None,
    new_facts: list[str],
    openai_base_url: str,
    api_key: str | None,
    model: str,
    max_tokens: int = 256,
) -> str | None:
    """Update the conversation summary based on new facts."""
    if not new_facts:
        return prior_summary
    system_prompt = SUMMARY_PROMPT
    user_parts = []
    if prior_summary:
        user_parts.append(f"Previous summary:\n{prior_summary}")
    user_parts.append("New facts:\n" + "\n".join(f"- {fact}" for fact in new_facts))
    prompt_text = "\n\n".join(user_parts)
    provider = OpenAIProvider(api_key=api_key or "dummy", base_url=openai_base_url)
    model_cfg = OpenAIChatModel(
        model_name=model,
        provider=provider,
        settings=ModelSettings(temperature=0.2, max_tokens=max_tokens),
    )
    agent = Agent(model=model_cfg, system_prompt=system_prompt, output_type=SummaryOutput)
    result = await agent.run(prompt_text)
    summary = result.output.summary if result.output else None
    return summary or prior_summary


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
    logger.info(
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

    if enable_summarization:
        prior_summary_entry = get_summary_entry(
            collection,
            conversation_id,
            role=_SUMMARY_ROLE,
        )
        prior_summary = prior_summary_entry.content if prior_summary_entry else None

        summary_start = perf_counter()
        new_summary = await update_summary(
            prior_summary=prior_summary,
            new_facts=facts,
            openai_base_url=openai_base_url,
            api_key=api_key,
            model=model,
        )
        logger.info(
            "Summary update completed in %.1f ms (conversation=%s)",
            _elapsed_ms(summary_start),
            conversation_id,
        )
        if new_summary:
            summary_obj = Summary(
                conversation_id=conversation_id,
                content=new_summary,
                created_at=datetime.now(UTC),
            )
            persist_summary(
                collection,
                memory_root=memory_root,
                summary=summary_obj,
            )

    if enable_git_versioning:
        await commit_changes(memory_root, f"Add facts to conversation {conversation_id}")
