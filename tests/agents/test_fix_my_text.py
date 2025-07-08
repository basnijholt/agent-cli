"""Tests for the autocorrect agent."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from agent_cli import config
from agent_cli.agents import autocorrect
from agent_cli.agents._command_setup import CommandConfig
from agent_cli.agents._config import GeneralConfig, LLMConfig
from agent_cli.agents._llm_common import process_with_llm
from agent_cli.agents._ui_common import display_input_text, display_output_with_clipboard


def test_system_prompt_and_instructions():
    """Test that the system prompt and instructions are properly defined."""
    assert autocorrect.SYSTEM_PROMPT
    assert "text correction tool" in autocorrect.SYSTEM_PROMPT.lower()
    assert "correct" in autocorrect.SYSTEM_PROMPT.lower()

    assert autocorrect.AGENT_INSTRUCTIONS
    assert "grammar" in autocorrect.AGENT_INSTRUCTIONS.lower()
    assert "spelling" in autocorrect.AGENT_INSTRUCTIONS.lower()


def test_display_output_with_clipboard_quiet_mode():
    """Test the display_output_with_clipboard function in quiet mode with real output."""
    # Test normal correction
    with patch("agent_cli.agents._ui_common.pyperclip.copy") as mock_copy:
        output = io.StringIO()
        general_cfg = GeneralConfig(
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=True,
            clipboard=True,
        )
        with redirect_stdout(output):
            display_output_with_clipboard(
                "Hello world!",
                original_text="hello world",
                elapsed=0.1,
                general_cfg=general_cfg,
            )

        assert output.getvalue().strip() == "Hello world!"
        mock_copy.assert_called_once_with("Hello world!")


def test_display_output_no_correction_needed():
    """Test the display_output_with_clipboard function when no correction is needed."""
    with patch("agent_cli.agents._ui_common.pyperclip.copy") as mock_copy:
        output = io.StringIO()
        general_cfg = GeneralConfig(
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=True,
            clipboard=True,
        )
        with redirect_stdout(output):
            display_output_with_clipboard(
                "Hello world!",
                original_text="Hello world!",
                elapsed=0.1,
                general_cfg=general_cfg,
            )

        assert output.getvalue().strip() == "✅ No changes needed."
        mock_copy.assert_called_once_with("Hello world!")


def test_display_output_verbose_mode():
    """Test the display_output_with_clipboard function in verbose mode with real console output."""
    mock_console = Console(file=io.StringIO(), width=80)
    with (
        patch("agent_cli.utils.console", mock_console),
        patch("agent_cli.agents._ui_common.pyperclip.copy") as mock_copy,
    ):
        general_cfg = GeneralConfig(
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=False,
            clipboard=True,
        )
        display_output_with_clipboard(
            "Hello world!",
            original_text="hello world",
            elapsed=0.25,
            general_cfg=general_cfg,
        )

        output = mock_console.file.getvalue()
        assert "Hello world!" in output
        assert "Output" in output
        assert "Success!" in output
        mock_copy.assert_called_once_with("Hello world!")


def test_display_input_text():
    """Test the display_input_text function."""
    mock_console = Console(file=io.StringIO(), width=80)
    with patch("agent_cli.utils.console", mock_console):
        general_cfg = GeneralConfig(
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=False,
            clipboard=True,
        )
        display_input_text("Test text here", general_cfg=general_cfg)
        output = mock_console.file.getvalue()
        assert "Test text here" in output
        assert "Original Text" in output


def test_display_input_text_quiet_mode():
    """Test display_input_text with quiet mode (should not print anything)."""
    mock_console = Console(file=io.StringIO(), width=80)
    with patch("agent_cli.utils.console", mock_console):
        general_cfg = GeneralConfig(
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=True,
            clipboard=True,
        )
        # This should not raise an exception or print anything
        display_input_text("Test text", general_cfg=general_cfg)
        assert mock_console.file.getvalue() == ""


@pytest.mark.asyncio
@patch("agent_cli.agents._llm_common.build_agent")
async def test_process_with_llm_integration(mock_build_agent: MagicMock) -> None:
    """Test process_with_llm with a more realistic mock setup."""
    # Create a mock agent that behaves more like the real thing
    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "This is corrected text."
    mock_agent.run = AsyncMock(return_value=mock_result)
    mock_build_agent.return_value = mock_agent

    llm_config = LLMConfig(model="test-model", ollama_host="http://localhost:11434")

    # Test the function
    result = await process_with_llm(
        "this is text",
        llm_config,
        autocorrect.SYSTEM_PROMPT,
        autocorrect.AGENT_INSTRUCTIONS,
        autocorrect.INPUT_TEMPLATE,
    )

    # Verify the result
    assert result["success"] is True
    assert result["output"] == "This is corrected text."
    assert isinstance(result["elapsed"], float)
    assert result["elapsed"] >= 0
    assert result["error"] is None

    # Verify the agent was called correctly
    mock_build_agent.assert_called_once_with(
        model="test-model",
        ollama_host="http://localhost:11434",
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    expected_input = "\n<text-to-correct>\nthis is text\n</text-to-correct>\n\nPlease correct any grammar, spelling, or punctuation errors in the text above.\n"
    mock_agent.run.assert_called_once_with(expected_input)


def test_configuration_constants():
    """Test that configuration constants are properly set."""
    # Test that OLLAMA_HOST has a reasonable value (could be localhost or custom)
    assert config.OLLAMA_HOST
    assert config.OLLAMA_HOST.startswith("http")  # Should be a valid URL

    # Test that DEFAULT_MODEL is set
    assert config.DEFAULT_MODEL
    assert isinstance(config.DEFAULT_MODEL, str)


@pytest.mark.asyncio
@patch("agent_cli.agents._llm_common.build_agent")
@patch("agent_cli.agents.autocorrect.get_clipboard_text")
async def test_autocorrect_command_with_text(
    mock_get_clipboard: MagicMock,
    mock_build_agent: MagicMock,
) -> None:
    """Test the autocorrect command with text provided as an argument."""
    # Setup
    mock_get_clipboard.return_value = "from clipboard"
    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "Corrected text."
    mock_agent.run = AsyncMock(return_value=mock_result)
    mock_build_agent.return_value = mock_agent

    llm_config = LLMConfig(model=config.DEFAULT_MODEL, ollama_host=config.OLLAMA_HOST)
    general_cfg = GeneralConfig(
        log_level="WARNING",
        log_file=None,
        list_devices=False,
        quiet=True,
    )

    config_obj = CommandConfig(general_cfg=general_cfg, llm_config=llm_config)

    with patch("agent_cli.agents._ui_common.pyperclip.copy"):
        await autocorrect._async_autocorrect(
            text="input text",
            config=config_obj,
        )

    # Assertions
    mock_get_clipboard.assert_not_called()
    mock_build_agent.assert_called_once_with(
        model=config.DEFAULT_MODEL,
        ollama_host=config.OLLAMA_HOST,
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    expected_input = "\n<text-to-correct>\ninput text\n</text-to-correct>\n\nPlease correct any grammar, spelling, or punctuation errors in the text above.\n"
    mock_agent.run.assert_called_once_with(expected_input)


@pytest.mark.asyncio
@patch("agent_cli.agents._llm_common.build_agent")
@patch("agent_cli.agents.autocorrect.get_clipboard_text")
async def test_autocorrect_command_from_clipboard(
    mock_get_clipboard: MagicMock,
    mock_build_agent: MagicMock,
) -> None:
    """Test the autocorrect command reading from the clipboard."""
    # Setup
    mock_get_clipboard.return_value = "clipboard text"
    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "Corrected clipboard text."
    mock_agent.run = AsyncMock(return_value=mock_result)
    mock_build_agent.return_value = mock_agent

    llm_config = LLMConfig(model=config.DEFAULT_MODEL, ollama_host=config.OLLAMA_HOST)
    general_cfg = GeneralConfig(
        log_level="WARNING",
        log_file=None,
        list_devices=False,
        quiet=True,
    )

    config_obj = CommandConfig(general_cfg=general_cfg, llm_config=llm_config)

    with patch("agent_cli.agents._ui_common.pyperclip.copy"):
        await autocorrect._async_autocorrect(
            text=None,  # No text argument provided
            config=config_obj,
        )

    # Assertions
    mock_get_clipboard.assert_called_once_with(quiet=True)
    mock_build_agent.assert_called_once_with(
        model=config.DEFAULT_MODEL,
        ollama_host=config.OLLAMA_HOST,
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    expected_input = "\n<text-to-correct>\nclipboard text\n</text-to-correct>\n\nPlease correct any grammar, spelling, or punctuation errors in the text above.\n"
    mock_agent.run.assert_called_once_with(expected_input)


@pytest.mark.asyncio
@patch("agent_cli.agents._llm_common.process_with_llm", new_callable=AsyncMock)
@patch("agent_cli.agents.autocorrect.get_clipboard_text", return_value=None)
async def test_async_autocorrect_no_text(
    mock_get_clipboard_text: MagicMock,
    mock_process_with_llm: AsyncMock,
) -> None:
    """Test the async_autocorrect function when no text is provided."""
    llm_config = LLMConfig(model="test", ollama_host="test")
    general_cfg = GeneralConfig(
        log_level="WARNING",
        log_file=None,
        list_devices=False,
        quiet=True,
    )

    config_obj = CommandConfig(general_cfg=general_cfg, llm_config=llm_config)

    await autocorrect._async_autocorrect(
        text=None,
        config=config_obj,
    )
    mock_process_with_llm.assert_not_called()
    mock_get_clipboard_text.assert_called_once()
