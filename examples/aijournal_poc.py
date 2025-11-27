#!/usr/bin/env python3
"""Minimal AI Journal proof-of-concept using MemoryClient.

This validates the core hypothesis: MemoryClient can serve as the
foundation for a personal knowledge system (AI journal).

Usage:
    # Add a journal entry
    python examples/aijournal_poc.py add "Today I learned about quantum computing at work"

    # Search memories
    python examples/aijournal_poc.py search "what did I learn?"

    # Interactive chat with memory
    python examples/aijournal_poc.py chat "What have I been working on lately?"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

import httpx

from agent_cli.memory.client import MemoryClient

# Enable debug logging for memory module
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Enable DEBUG for memory ingest to see full prompts
logging.getLogger("agent_cli.memory._ingest").setLevel(logging.DEBUG)


# Defaults for local AI setup
DEFAULT_BASE_URL = "http://192.168.1.143:9292/v1"
DEFAULT_MODEL = "gpt-oss-high:20b"
DEFAULT_EMBEDDING_MODEL = "embeddinggemma:300m"


def get_client(model: str | None = None) -> tuple[MemoryClient, str]:
    """Initialize the memory client with sensible defaults.

    Returns:
        Tuple of (client, model_name)

    """
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    model_name = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    embedding_model = os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    api_key = os.environ.get("OPENAI_API_KEY", "not-needed-for-local")

    print(f"Using: {base_url}")
    print(f"  Chat model: {model_name}")
    print(f"  Embedding model: {embedding_model}")

    return MemoryClient(
        memory_path=Path("~/.aijournal").expanduser(),
        openai_base_url=base_url,
        chat_api_key=api_key,
        embedding_api_key=api_key,
        embedding_model=embedding_model,
        enable_summarization=True,
        enable_git_versioning=False,  # Keep it simple for POC
        score_threshold=0.1,  # Lower threshold for local models
    ), model_name


async def cmd_add(text: str) -> None:
    """Add a journal entry."""
    client, model = get_client()
    print(f"Adding entry: {text[:50]}...")
    await client.add(text, conversation_id="journal", model=model)
    print("✓ Entry processed and facts extracted")


async def cmd_search(query: str, top_k: int = 5) -> None:
    """Search memories."""
    client, model = get_client()
    print(f"Searching for: {query}\n")

    result = await client.search(query, conversation_id="journal", top_k=top_k, model=model)

    if not result.entries:
        print("No relevant memories found.")
        return

    for i, entry in enumerate(result.entries, 1):
        print(f"{i}. [{entry.role}] {entry.content}")
        print(f"   Score: {entry.score:.3f} | Created: {entry.created_at[:10]}")
        print()


def cmd_show() -> None:
    """Show all stored memories (what the system knows about you)."""
    client, _ = get_client()
    print("=== What I know about you ===\n")

    entries = client.list_all(conversation_id="journal")

    if not entries:
        print("No memories stored yet. Add some journal entries first!")
        return

    # Sort by created_at
    entries.sort(key=lambda x: x["created_at"], reverse=True)

    for i, entry in enumerate(entries, 1):
        date = entry["created_at"][:10] if entry["created_at"] else "unknown"
        print(f"{i}. [{date}] {entry['content']}")

    print(f"\n--- Total: {len(entries)} memories ---")


PROFILE_PROMPT = """Based on the following facts about a person, create a brief profile summary.
Organize the information into categories like:
- **Identity**: Name, relationships, occupation
- **Interests & Activities**: Hobbies, regular activities
- **Goals & Values**: What they care about, what they're working towards
- **Recent Events**: Notable recent happenings

Only include categories that have relevant information. Be concise.

Facts:
{facts}

Profile Summary:"""


async def cmd_profile() -> None:
    """Generate a profile summary from stored memories."""
    client, model = get_client()

    entries = client.list_all(conversation_id="journal")

    if not entries:
        print("No memories stored yet. Add some journal entries first!")
        return

    # Format facts for the prompt
    facts = "\n".join(f"- {e['content']}" for e in entries)
    prompt = PROFILE_PROMPT.format(facts=facts)

    print("=== Your Profile ===\n")
    print("(Generating profile from stored memories...)\n")

    # Direct LLM call (bypasses memory storage)
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("OPENAI_API_KEY", "not-needed-for-local")

    async with httpx.AsyncClient(timeout=120.0) as http:
        response = await http.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
        )
        data = response.json()

    choices = data.get("choices", [])
    if choices:
        profile = choices[0].get("message", {}).get("content", "")
        print(profile)

    print(f"\n--- Based on {len(entries)} memories ---")


CHAT_SYSTEM_PROMPT = """You are a helpful AI assistant with memory of the user.

Here's what you know about the user:
{profile}

Use this knowledge naturally in your responses. Be helpful and personable."""


async def cmd_chat(question: str, with_profile: bool = True) -> None:
    """Chat with memory-augmented LLM."""
    client, model = get_client()

    # Build profile context
    profile_text = ""
    if with_profile:
        entries = client.list_all(conversation_id="journal")
        if entries:
            profile_text = "\n".join(f"- {e['content']}" for e in entries)

    print(f"Question: {question}\n")

    # Build messages with profile context
    messages: list[dict[str, str]] = []
    if profile_text:
        system_prompt = CHAT_SYSTEM_PROMPT.format(profile=profile_text)
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": question})

    # Direct LLM call with profile context
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("OPENAI_API_KEY", "not-needed-for-local")

    async with httpx.AsyncClient(timeout=120.0) as http:
        response = await http.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
            },
        )
        data = response.json()

    choices = data.get("choices", [])
    if choices:
        reply = choices[0].get("message", {}).get("content", "")
        print(f"Answer: {reply}")

    if profile_text:
        entry_count = len(client.list_all(conversation_id="journal"))
        print(f"\n--- Using profile with {entry_count} memories ---")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="AI Journal POC")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a journal entry")
    add_parser.add_argument("text", help="The journal entry text")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search memories")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of results")

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Chat with memory")
    chat_parser.add_argument("question", help="Question to ask")

    # Show command - display what the system knows about you
    subparsers.add_parser("show", help="Show all stored memories")

    # Profile command - generate a profile summary
    subparsers.add_parser("profile", help="Generate profile from memories")

    args = parser.parse_args()

    if args.command == "add":
        asyncio.run(cmd_add(args.text))
    elif args.command == "search":
        asyncio.run(cmd_search(args.query, args.top_k))
    elif args.command == "chat":
        asyncio.run(cmd_chat(args.question))
    elif args.command == "show":
        cmd_show()
    elif args.command == "profile":
        asyncio.run(cmd_profile())


if __name__ == "__main__":
    main()
