"""Common command setup utilities for agents."""

from __future__ import annotations

from contextlib import suppress
from typing import (
    TYPE_CHECKING,
    NamedTuple,
)

from agent_cli.agents._config import GeneralConfig, LLMConfig
from agent_cli.utils import stop_or_status_or_toggle

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from types import TracebackType
    from typing import Self


class CommandConfig(NamedTuple):
    """Configuration for a command."""

    general_cfg: GeneralConfig
    llm_config: LLMConfig | None = None


def setup_command(
    *,
    # Command info
    process_name: str,
    command_description: str,
    # Process control
    stop: bool,
    status: bool,
    toggle: bool,
    # General options
    log_level: str,
    log_file: str | None,
    quiet: bool,
    list_devices: bool = False,
    clipboard: bool = True,
    # LLM options (optional)
    model: str | None = None,
    ollama_host: str | None = None,
    llm_provider: str | None = None,
    openai_api_key: str | None = None,
) -> CommandConfig | None:
    """Common setup for agent commands.

    Returns:
        CommandConfig if setup successful, None if command was handled (stop/status/toggle)

    """
    # Import locally to avoid circular imports
    from agent_cli.cli import setup_logging  # noqa: PLC0415

    setup_logging(log_level, log_file, quiet=quiet)

    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=clipboard,
    )

    # Handle process control commands
    if stop_or_status_or_toggle(
        process_name,
        command_description,
        stop,
        status,
        toggle,
        quiet=general_cfg.quiet,
    ):
        return None

    # Create LLM config if model specified
    llm_config = None
    if model:
        llm_config = LLMConfig(
            model=model,
            llm_provider=llm_provider or "ollama",
            ollama_host=ollama_host,
            openai_api_key=openai_api_key,
        )

    return CommandConfig(general_cfg=general_cfg, llm_config=llm_config)


def with_process_management(process_name: str) -> AbstractContextManager:
    """Get context manager for process management."""
    from agent_cli import process_manager  # noqa: PLC0415

    class ProcessContext:
        def __enter__(self) -> Self:
            self.pid_context = process_manager.pid_file_context(process_name)
            self.kbd_context = suppress(KeyboardInterrupt)
            self.pid_context.__enter__()
            self.kbd_context.__enter__()
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            self.kbd_context.__exit__(exc_type, exc_val, exc_tb)
            self.pid_context.__exit__(exc_type, exc_val, exc_tb)

    return ProcessContext()
