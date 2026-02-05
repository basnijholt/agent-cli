"""Ingestion logic for memory (LLM Extraction, Reconciliation, Summarization)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

from agent_cli.memory._git import commit_changes
from agent_cli.memory._persistence import delete_memory_files, persist_entries, persist_summary
from agent_cli.memory._prompt import (
    FACT_INSTRUCTIONS,
    FACT_SYSTEM_PROMPT,
    SUMMARY_PROMPT,
    UPDATE_MEMORY_PROMPT,
)
from agent_cli.memory._retrieval import gather_relevant_existing_memories
from agent_cli.memory._store import delete_entries, get_summary_entry
from agent_cli.memory.entities import Fact, Summary
from agent_cli.memory.models import (
    MemoryAdd,
    MemoryDecision,
    MemoryDelete,
    MemoryIgnore,
    MemoryUpdate,
    SummaryOutput,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

LOGGER = logging.getLogger(__name__)

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

    import httpx  # noqa: PLC0415
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
            text = dec.text.strip()
            if text:
                # Update existing memory: delete old, add new
                orig = id_map[dec.id]  # Guaranteed valid by output_validator
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
        elif isinstance(dec, MemoryDelete):
            to_delete.append(id_map[dec.id])  # Guaranteed valid by output_validator
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

    import httpx  # noqa: PLC0415
    from pydantic_ai import Agent, ModelRetry, PromptedOutput  # noqa: PLC0415
    from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIChatModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415
    from pydantic_ai.settings import ModelSettings  # noqa: PLC0415

    id_map: dict[int, str] = {idx: mem.id for idx, mem in enumerate(existing)}
    existing_json = [{"id": idx, "text": mem.content} for idx, mem in enumerate(existing)]
    existing_ids = set(id_map.keys())

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

    from pydantic_ai import Agent  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIChatModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415
    from pydantic_ai.settings import ModelSettings  # noqa: PLC0415

    system_prompt = SUMMARY_PROMPT
    user_parts: list[str] = []
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
    return result.output.summary or prior_summary


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
        LOGGER.info(
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
