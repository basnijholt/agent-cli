"""Summarize text files or stdin using adaptive hierarchical summarization."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from enum import Enum
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import typer

from agent_cli import config, opts
from agent_cli.cli import app
from agent_cli.core.utils import (
    console,
    create_status,
    print_command_line_args,
    print_error_message,
    print_input_panel,
    print_output_panel,
    print_with_style,
    setup_logging,
)
from agent_cli.summarizer import SummarizationError, SummarizerConfig, summarize
from agent_cli.summarizer._utils import count_tokens

if TYPE_CHECKING:
    from agent_cli.summarizer import SummaryResult


class ContentType(str, Enum):
    """Content type for specialized summarization prompts."""

    general = "general"
    conversation = "conversation"
    journal = "journal"
    document = "document"


class OutputFormat(str, Enum):
    """Output format for the summarization result."""

    text = "text"
    json = "json"
    full = "full"


def _read_input(file_path: Path | None) -> str | None:
    """Read input from file or stdin."""
    if file_path:
        if not file_path.exists():
            print_error_message(
                f"File not found: {file_path}",
                "Please check the file path and try again.",
            )
            return None
        return file_path.read_text(encoding="utf-8")

    # Read from stdin
    if sys.stdin.isatty():
        print_error_message(
            "No input provided",
            "Provide a file path or pipe content via stdin.",
        )
        return None

    return sys.stdin.read()


def _display_input_preview(
    content: str,
    token_count: int,
    *,
    quiet: bool,
    max_preview_chars: int = 500,
) -> None:
    """Display a preview of the input content."""
    if quiet:
        return

    preview = content[:max_preview_chars]
    if len(content) > max_preview_chars:
        preview += f"\n... [{len(content) - max_preview_chars} more characters]"

    print_input_panel(
        preview,
        title=f"Input ({token_count:,} tokens)",
    )


def _display_result(
    result: SummaryResult,
    elapsed: float,
    output_format: OutputFormat,
    *,
    quiet: bool,
) -> None:
    """Display the summarization result."""
    if output_format == OutputFormat.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        return

    if output_format == OutputFormat.full:
        _display_full_result(result, elapsed, quiet=quiet)
        return

    # Text output - just the summary
    if quiet:
        if result.summary:
            print(result.summary)
    elif result.summary:
        print_output_panel(
            result.summary,
            title=f"Summary (Level: {result.level.name})",
            subtitle=f"[dim]{result.output_tokens:,} tokens | {result.compression_ratio:.1%} of original | {elapsed:.2f}s[/dim]",
        )
    else:
        print_with_style(
            f"No summary generated (input too short: {result.input_tokens} tokens)",
            style="yellow",
        )


def _display_full_result(
    result: SummaryResult,
    elapsed: float,
    *,
    quiet: bool,
) -> None:
    """Display full hierarchical result with all levels."""
    if quiet:
        if result.summary:
            print(result.summary)
        return

    console.print()
    console.print("[bold cyan]Summarization Result[/bold cyan]")
    console.print(f"  Level: [bold]{result.level.name}[/bold]")
    console.print(f"  Input tokens: [bold]{result.input_tokens:,}[/bold]")
    console.print(f"  Output tokens: [bold]{result.output_tokens:,}[/bold]")
    console.print(f"  Compression: [bold]{result.compression_ratio:.1%}[/bold]")
    console.print(f"  Time: [bold]{elapsed:.2f}s[/bold]")
    console.print()

    if result.hierarchical:
        if result.hierarchical.l1_summaries:
            console.print(
                f"[bold yellow]L1 Chunk Summaries "
                f"({len(result.hierarchical.l1_summaries)} chunks)[/bold yellow]",
            )
            for cs in result.hierarchical.l1_summaries:
                console.print(
                    f"\n[dim]--- Chunk {cs.chunk_index + 1} "
                    f"({cs.source_tokens:,} → {cs.token_count:,} tokens) ---[/dim]",
                )
                console.print(cs.content)

        if result.hierarchical.l2_summaries:
            console.print(
                f"\n[bold yellow]L2 Group Summaries "
                f"({len(result.hierarchical.l2_summaries)} groups)[/bold yellow]",
            )
            for idx, l2_summary in enumerate(result.hierarchical.l2_summaries):
                console.print(f"\n[dim]--- Group {idx + 1} ---[/dim]")
                console.print(l2_summary)

        console.print("\n[bold green]L3 Final Summary[/bold green]")
        print_output_panel(result.hierarchical.l3_summary, title="Final Summary")
    elif result.summary:
        print_output_panel(
            result.summary,
            title=f"Summary ({result.level.name})",
        )


def _get_llm_config(
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
) -> tuple[str, str, str | None]:
    """Get openai_base_url, model, and api_key from provider config."""
    if provider_cfg.llm_provider == "ollama":
        # Ollama uses OpenAI-compatible API at /v1
        base_url = ollama_cfg.llm_ollama_host.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return base_url, ollama_cfg.llm_ollama_model, None
    if provider_cfg.llm_provider == "openai":
        base_url = openai_llm_cfg.openai_base_url or "https://api.openai.com/v1"
        return base_url, openai_llm_cfg.llm_openai_model, openai_llm_cfg.openai_api_key
    # gemini
    return (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        gemini_llm_cfg.llm_gemini_model,
        gemini_llm_cfg.gemini_api_key,
    )


async def _async_summarize(
    content: str,
    *,
    content_type: ContentType,
    prior_summary: str | None,
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    general_cfg: config.General,
    chunk_size: int,
    chunk_overlap: int,
    max_concurrent_chunks: int,
    output_format: OutputFormat,
) -> None:
    """Asynchronous summarization entry point."""
    setup_logging(general_cfg.log_level, general_cfg.log_file, quiet=general_cfg.quiet)

    openai_base_url, model, api_key = _get_llm_config(
        provider_cfg,
        ollama_cfg,
        openai_llm_cfg,
        gemini_llm_cfg,
    )

    token_count = count_tokens(content, model)
    _display_input_preview(content, token_count, quiet=general_cfg.quiet)

    summarizer_config = SummarizerConfig(
        openai_base_url=openai_base_url,
        model=model,
        api_key=api_key,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        max_concurrent_chunks=max_concurrent_chunks,
    )

    try:
        if not general_cfg.quiet:
            status = create_status(f"Summarizing with {model}...", "bold yellow")
        else:
            status = contextlib.nullcontext()

        with status:
            start_time = time.monotonic()
            result = await summarize(
                content,
                summarizer_config,
                prior_summary=prior_summary,
                content_type=content_type.value,
            )
            elapsed = time.monotonic() - start_time

        _display_result(result, elapsed, output_format, quiet=general_cfg.quiet)

    except SummarizationError as e:
        print_error_message(
            str(e),
            f"Check that your LLM server is running at {openai_base_url}",
        )
        sys.exit(1)
    except Exception as e:
        print_error_message(str(e), "An unexpected error occurred during summarization.")
        sys.exit(1)


@app.command("summarize")
def summarize_command(
    *,
    file_path: Path | None = typer.Argument(  # noqa: B008
        None,
        help="Path to file to summarize. If not provided, reads from stdin.",
    ),
    # --- Content Options ---
    content_type: ContentType = typer.Option(  # noqa: B008
        ContentType.general,
        "--type",
        "-t",
        help="Content type for specialized summarization prompts.",
        rich_help_panel="Content Options",
    ),
    prior_summary: str | None = typer.Option(
        None,
        "--prior-summary",
        help="Prior summary to integrate with (for rolling summaries).",
        rich_help_panel="Content Options",
    ),
    prior_summary_file: Path | None = typer.Option(  # noqa: B008
        None,
        "--prior-summary-file",
        help="File containing prior summary to integrate with.",
        rich_help_panel="Content Options",
    ),
    # --- Chunking Options ---
    chunk_size: int = typer.Option(
        3000,
        "--chunk-size",
        help="Target token count per chunk for hierarchical summarization.",
        rich_help_panel="Chunking Options",
    ),
    chunk_overlap: int = typer.Option(
        200,
        "--chunk-overlap",
        help="Token overlap between chunks for context continuity.",
        rich_help_panel="Chunking Options",
    ),
    max_concurrent_chunks: int = typer.Option(
        5,
        "--max-concurrent",
        help="Maximum number of chunks to process in parallel.",
        rich_help_panel="Chunking Options",
    ),
    # --- Output Options ---
    output_format: OutputFormat = typer.Option(  # noqa: B008
        OutputFormat.text,
        "--output",
        "-o",
        help="Output format: 'text' (summary only), 'json' (full result), 'full' (all levels).",
        rich_help_panel="Output Options",
    ),
    # --- Provider Selection ---
    llm_provider: str = opts.LLM_PROVIDER,
    # --- LLM Configuration ---
    # Ollama (local service)
    llm_ollama_model: str = opts.LLM_OLLAMA_MODEL,
    llm_ollama_host: str = opts.LLM_OLLAMA_HOST,
    # OpenAI
    llm_openai_model: str = opts.LLM_OPENAI_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    # Gemini
    llm_gemini_model: str = opts.LLM_GEMINI_MODEL,
    gemini_api_key: str | None = opts.GEMINI_API_KEY,
    # --- General Options ---
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Summarize text using adaptive hierarchical summarization.

    Reads from a file or stdin and produces a summary scaled to the input complexity:

    - NONE (<100 tokens): No summary needed
    - BRIEF (100-500): Single sentence
    - STANDARD (500-3000): Paragraph
    - DETAILED (3000-15000): Chunked with meta-summary
    - HIERARCHICAL (>15000): Full L1/L2/L3 tree

    Examples:
        # Summarize a file
        agent-cli summarize document.txt

        # Summarize with conversation-specific prompts
        agent-cli summarize chat.txt --type conversation

        # Pipe content from stdin
        cat book.txt | agent-cli summarize

        # Get full hierarchical output
        agent-cli summarize large_document.txt --output full

        # Use OpenAI instead of Ollama
        agent-cli summarize notes.md --llm-provider openai

    """
    if print_args:
        print_command_line_args(locals())

    # Create config objects following the standard pattern
    provider_cfg = config.ProviderSelection(
        llm_provider=llm_provider,
        asr_provider="wyoming",  # Not used, but required by model
        tts_provider="wyoming",  # Not used, but required by model
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model=llm_ollama_model,
        llm_ollama_host=llm_ollama_host,
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=llm_openai_model,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model=llm_gemini_model,
        gemini_api_key=gemini_api_key,
    )
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        clipboard=False,  # summarize doesn't use clipboard
    )

    # Read content
    content = _read_input(file_path)
    if content is None:
        raise typer.Exit(1)

    if not content.strip():
        print_error_message("Empty input", "The input file or stdin is empty.")
        raise typer.Exit(1)

    # Handle prior summary from file
    actual_prior_summary = prior_summary
    if prior_summary_file:
        if not prior_summary_file.exists():
            print_error_message(
                f"Prior summary file not found: {prior_summary_file}",
                "Please check the file path.",
            )
            raise typer.Exit(1)
        actual_prior_summary = prior_summary_file.read_text(encoding="utf-8")

    asyncio.run(
        _async_summarize(
            content,
            content_type=content_type,
            prior_summary=actual_prior_summary,
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            general_cfg=general_cfg,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            max_concurrent_chunks=max_concurrent_chunks,
            output_format=output_format,
        ),
    )
