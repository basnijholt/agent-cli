#!/usr/bin/env python3
"""Integration test for RAG server with a real LLM."""

import asyncio
import shutil
import sys
from pathlib import Path

import httpx
from rich.console import Console

console = Console()

RAG_PORT = 8000
LLAMA_URL = "http://localhost:9292"  # User provided
DOCS_FOLDER = Path("./temp_rag_docs")
DB_FOLDER = Path("./temp_rag_db")


async def main() -> None:  # noqa: C901, PLR0912, PLR0915
    """Run integration test."""
    if DOCS_FOLDER.exists():
        shutil.rmtree(DOCS_FOLDER)
    if DB_FOLDER.exists():
        shutil.rmtree(DB_FOLDER)

    DOCS_FOLDER.mkdir(parents=True)
    DB_FOLDER.mkdir(parents=True)

    console.print("[bold blue]Starting RAG Integration Test[/bold blue]")

    # Check if LLM is running
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{LLAMA_URL}/health")
            if resp.status_code != 200:  # noqa: PLR2004
                console.print(
                    f"[bold red]LLM Server at {LLAMA_URL} returned {resp.status_code}.[/bold red]",
                )
                # Proceed anyway, maybe it doesn't have health endpoint
        except Exception as e:
            console.print(
                f"[bold red]Could not connect to LLM Server at {LLAMA_URL}: {e}[/bold red]",
            )
            console.print("[yellow]Please ensure llama-server is running on port 9292.[/yellow]")
            sys.exit(1)

    # Start RAG Server
    cmd = [
        sys.executable,
        "-m",
        "agent_cli.cli",
        "rag-server",
        "--docs-folder",
        str(DOCS_FOLDER),
        "--chroma-path",
        str(DB_FOLDER),
        "--llama-url",
        LLAMA_URL,
        "--port",
        str(RAG_PORT),
    ]

    console.print(f"Running: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        # Wait for server to start
        console.print("Waiting for RAG server to start...")
        rag_url = f"http://localhost:{RAG_PORT}"

        server_up = False
        for _ in range(20):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{rag_url}/health")
                    if resp.status_code == 200:  # noqa: PLR2004
                        server_up = True
                        break
            except Exception:
                await asyncio.sleep(0.5)

        if not server_up:
            console.print("[bold red]RAG Server failed to start.[/bold red]")
            sys.exit(1)

        console.print("[green]RAG Server is up![/green]")

        # Create a document
        secret_info = "The secret code for the vault is 'BlueBananas123'."  # noqa: S105
        doc_path = DOCS_FOLDER / "secret.txt"
        doc_path.write_text(f"Confidential Information:\n{secret_info}", encoding="utf-8")
        console.print(f"Created document: {doc_path}")

        # Wait for indexing (poll /files endpoint)
        console.print("Waiting for indexing...")
        indexed = False
        for _ in range(20):
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{rag_url}/files")
                data = resp.json()
                if data["total"] > 0:
                    indexed = True
                    break
            await asyncio.sleep(0.5)

        if not indexed:
            console.print("[bold red]File was not indexed.[/bold red]")
            sys.exit(1)

        console.print("[green]File indexed![/green]")

        # Query
        query = "What is the secret code for the vault?"
        console.print(f"Querying: '{query}'")

        payload = {
            "model": "gpt-3.5-turbo",  # Generic model name, llama.cpp ignores it often or maps it
            "messages": [{"role": "user", "content": query}],
            "rag_top_k": 1,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{rag_url}/v1/chat/completions", json=payload)

        if resp.status_code != 200:  # noqa: PLR2004
            console.print(f"[bold red]Query failed: {resp.text}[/bold red]")
            sys.exit(1)

        result = resp.json()
        answer = result["choices"][0]["message"]["content"]
        console.print(f"[bold cyan]Answer:[/bold cyan] {answer}")

        if "BlueBananas123" in answer:
            console.print("[bold green]SUCCESS: Secret code found in answer![/bold green]")
        else:
            console.print(
                "[bold yellow]WARNING: Secret code NOT found in answer. Check retrieval or LLM capability.[/bold yellow]",
            )
            if "rag_sources" in result:
                console.print(f"Sources: {result['rag_sources']}")

    finally:
        console.print("Shutting down RAG server...")
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()

        # Cleanup
        if DOCS_FOLDER.exists():
            shutil.rmtree(DOCS_FOLDER)
        if DB_FOLDER.exists():
            shutil.rmtree(DB_FOLDER)


if __name__ == "__main__":
    asyncio.run(main())
