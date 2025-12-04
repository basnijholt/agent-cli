#!/usr/bin/env python3
"""Integration test for RAG proxy with a real LLM."""

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

console = Console()

RAG_PORT = 8001
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

    llm_available = False
    # Check if LLM is running
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{LLAMA_URL}/health")
            if resp.status_code == 200:  # noqa: PLR2004
                llm_available = True
                console.print(f"[green]LLM Server found at {LLAMA_URL}.[/green]")
            else:
                console.print(
                    f"[yellow]LLM Server at {LLAMA_URL} returned {resp.status_code}. Skipping query tests.[/yellow]",
                )
        except Exception:
            console.print(
                f"[yellow]Could not connect to LLM Server at {LLAMA_URL}. Skipping query tests.[/yellow]",
            )

    # Start RAG Proxy
    cmd = [
        sys.executable,
        "-m",
        "agent_cli",
        "rag-proxy",
        "--docs-folder",
        str(DOCS_FOLDER),
        "--chroma-path",
        str(DB_FOLDER),
        "--openai-base-url",
        LLAMA_URL,
        "--port",
        str(RAG_PORT),
    ]

    console.print(f"Running: {' '.join(cmd)}")

    stdout_file = Path("rag_proxy_stdout.log").open("w")  # noqa: SIM115, ASYNC230
    stderr_file = Path("rag_proxy_stderr.log").open("w")  # noqa: SIM115, ASYNC230

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=stdout_file,
        stderr=stderr_file,
    )

    try:
        # Wait for server to start
        console.print("Waiting for RAG proxy to start...")
        rag_url = f"http://localhost:{RAG_PORT}"

        server_up = False
        for _ in range(20):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{rag_url}/health")
                    if resp.status_code == 200:  # noqa: PLR2004
                        server_up = True
                        break
            except Exception:
                await asyncio.sleep(0.5)

        if not server_up:
            console.print("[bold red]RAG Proxy failed to start.[/bold red]")
            stdout_file.close()
            stderr_file.close()
            console.print(f"Stdout: {Path('rag_proxy_stdout.log').read_text()}")
            console.print(f"Stderr: {Path('rag_proxy_stderr.log').read_text()}")
            sys.exit(1)

        console.print("[green]RAG Proxy is up![/green]")

        # Create a document
        secret_info = "The secret code for the vault is 'BlueBananas123'."  # noqa: S105
        doc_path = DOCS_FOLDER / "secret.txt"
        doc_path.write_text(f"Confidential Information:\n{secret_info}", encoding="utf-8")
        console.print(f"Created document: {doc_path}")

        # Wait for indexing (poll /files endpoint)
        console.print("Waiting for indexing...")
        indexed = False
        for _ in range(20):
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{rag_url}/files")
                data = resp.json()
                if data["total"] > 0:
                    indexed = True
                    break
            await asyncio.sleep(0.5)

        if not indexed:
            console.print("[bold red]File was not indexed.[/bold red]")
            stdout_file.close()
            stderr_file.close()
            console.print(f"Stdout: {Path('rag_proxy_stdout.log').read_text()}")
            console.print(f"Stderr: {Path('rag_proxy_stderr.log').read_text()}")
            sys.exit(1)

        console.print("[green]File indexed![/green]")

        if llm_available:
            # Fetch available models
            model_name = "gpt-3.5-turbo"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{LLAMA_URL}/v1/models")
                    if resp.status_code == 200:  # noqa: PLR2004
                        models = resp.json()["data"]
                        if models:
                            model_name = models[0]["id"]
                            console.print(f"[blue]Using model: {model_name}[/blue]")
            except Exception:
                console.print(
                    "[yellow]Could not fetch models, defaulting to gpt-3.5-turbo[/yellow]",
                )

            # Query
            query = "What is the secret code for the vault?"
            console.print(f"Querying: '{query}'")

            payload: dict[str, Any] = {
                "model": model_name,
                "messages": [{"role": "user", "content": query}],
                "rag_top_k": 1,
            }
            url = f"{rag_url}/v1/chat/completions"
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)

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
        else:
            console.print(
                "[blue]Skipping query test (LLM not available). Indexing verification successful.[/blue]",
            )

    finally:
        console.print("Shutting down RAG proxy...")
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()

        stdout_file.close()
        stderr_file.close()

        # Cleanup
        if DOCS_FOLDER.exists():
            shutil.rmtree(DOCS_FOLDER)
        if DB_FOLDER.exists():
            shutil.rmtree(DB_FOLDER)

        Path("rag_proxy_stdout.log").unlink(missing_ok=True)
        Path("rag_proxy_stderr.log").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
