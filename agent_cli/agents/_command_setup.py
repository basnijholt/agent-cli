"""Common command setup utilities for agents."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from agent_cli.agents._config import GeneralConfig, LLMConfig
from agent_cli.cli import setup_logging
from agent_cli.utils import stop_or_status_or_toggle

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


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
) -> CommandConfig | None:
    """Common setup for agent commands.

    Returns:
        CommandConfig if setup successful, None if command was handled (stop/status/toggle)

    """
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
    if model and ollama_host:
        llm_config = LLMConfig(model=model, ollama_host=ollama_host)

    return CommandConfig(general_cfg=general_cfg, llm_config=llm_config)


def with_process_management(process_name: str) -> AbstractContextManager:
    """Get context manager for process management."""
    from contextlib import suppress  # noqa: PLC0415
    from typing import TYPE_CHECKING  # noqa: PLC0415

    from agent_cli import process_manager  # noqa: PLC0415

    if TYPE_CHECKING:
        from types import TracebackType  # noqa: PLC0415
        from typing import Self  # noqa: PLC0415

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
