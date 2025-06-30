"""Tests for the autocorrect agent."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from agent_cli import config
from agent_cli.agents import autocorrect
from agent_cli.agents._config import GeneralConfig, LLMConfig


def test_system_prompt_and_instructions():
    """Test that the system prompt and instructions are properly defined."""
    assert autocorrect.SYSTEM_PROMPT
    assert "editor" in autocorrect.SYSTEM_PROMPT.lower()
    assert "correct" in autocorrect.SYSTEM_PROMPT.lower()

    assert autocorrect.AGENT_INSTRUCTIONS
    assert "grammar" in autocorrect.AGENT_INSTRUCTIONS.lower()
    assert "spelling" in autocorrect.AGENT_INSTRUCTIONS.lower()


def test_display_result_quiet_mode():
    """Test the _display_result function in quiet mode with real output."""
    # Test normal correction
    with patch("agent_cli.agents.autocorrect.pyperclip.copy") as mock_copy:
        output = io.StringIO()
        with redirect_stdout(output):
            autocorrect._display_result(
                "Hello world!",
                "hello world",
                0.1,
                simple_output=True,
                console=None,
            )

        assert output.getvalue().strip() == "Hello world!"
        mock_copy.assert_called_once_with("Hello world!")


def test_display_result_no_correction_needed():
    """Test the _display_result function when no correction is needed."""
    with patch("agent_cli.agents.autocorrect.pyperclip.copy") as mock_copy:
        output = io.StringIO()
        with redirect_stdout(output):
            autocorrect._display_result(
                "Hello world!",
                "Hello world!",
                0.1,
                simple_output=True,
                console=None,
            )

        assert output.getvalue().strip() == "✅ No correction needed."
        mock_copy.assert_called_once_with("Hello world!")


def test_display_result_verbose_mode():
    """Test the _display_result function in verbose mode with real console output."""
    console = Console(file=io.StringIO(), width=80)

    with patch("agent_cli.agents.autocorrect.pyperclip.copy") as mock_copy:
        autocorrect._display_result(
            "Hello world!",
            "hello world",
            0.25,
            simple_output=False,
            console=console,
        )

        output = console.file.getvalue()
        assert "Hello world!" in output
        assert "Corrected Text" in output
        assert "Success!" in output
        mock_copy.assert_called_once_with("Hello world!")


def test_display_original_text():
    """Test the display_original_text function."""
    console = Console(file=io.StringIO(), width=80)

    autocorrect.display_original_text("Test text here", console)

    output = console.file.getvalue()
    assert "Test text here" in output
    assert "Original Text" in output


def test_display_original_text_none_console():
    """Test display_original_text with None console (should not crash)."""
    # This should not raise an exception
    autocorrect.display_original_text("Test text", None)


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect.build_agent")
async def test_process_text_integration(mock_build_agent: MagicMock) -> None:
    """Test process_text with a more realistic mock setup."""
    # Create a mock agent that behaves more like the real thing
    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "This is corrected text."
    mock_agent.run = AsyncMock(return_value=mock_result)
    mock_build_agent.return_value = mock_agent

    # Test the function
    result, elapsed = await autocorrect.process_text(
        "this is text",
        "test-model",
        "http://localhost:11434",
    )

    # Verify the result
    assert result == "This is corrected text."
    assert isinstance(elapsed, float)
    assert elapsed >= 0

    # Verify the agent was called correctly
    mock_build_agent.assert_called_once_with(
        model="test-model",
        ollama_host="http://localhost:11434",
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    mock_agent.run.assert_called_once_with("this is text")


def test_configuration_constants():
    """Test that configuration constants are properly set."""
    # Test that OLLAMA_HOST has a reasonable value (could be localhost or custom)
    assert config.OLLAMA_HOST
    assert config.OLLAMA_HOST.startswith("http")  # Should be a valid URL

    # Test that DEFAULT_MODEL is set
    assert config.DEFAULT_MODEL
    assert isinstance(config.DEFAULT_MODEL, str)


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect.build_agent")
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
    general_config = GeneralConfig(
        log_level="WARNING",
        log_file=None,
        quiet=True,
        console=None,
    )

    with patch("agent_cli.agents.autocorrect.pyperclip.copy"):
        await autocorrect.async_autocorrect(
            text="input text",
            llm_config=llm_config,
            general_config=general_config,
        )

    # Assertions
    mock_get_clipboard.assert_not_called()
    mock_build_agent.assert_called_once_with(
        model=config.DEFAULT_MODEL,
        ollama_host=config.OLLAMA_HOST,
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    mock_agent.run.assert_called_once_with("input text")


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect.build_agent")
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
    general_config = GeneralConfig(
        log_level="WARNING",
        log_file=None,
        quiet=True,
        console=None,
    )

    with patch("agent_cli.agents.autocorrect.pyperclip.copy"):
        await autocorrect.async_autocorrect(
            text=None,  # No text argument provided
            llm_config=llm_config,
            general_config=general_config,
        )

    # Assertions
    mock_get_clipboard.assert_called_once()
    mock_build_agent.assert_called_once_with(
        model=config.DEFAULT_MODEL,
        ollama_host=config.OLLAMA_HOST,
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    mock_agent.run.assert_called_once_with("clipboard text")


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect.process_text", new_callable=AsyncMock)
@patch("agent_cli.agents.autocorrect.get_clipboard_text", return_value=None)
async def test_async_autocorrect_no_text(
    mock_get_clipboard_text: MagicMock,
    mock_process_text: AsyncMock,
) -> None:
    """Test the async_autocorrect function when no text is provided."""
    llm_config = LLMConfig(model="test", ollama_host="test")
    general_config = GeneralConfig(
        log_level="WARNING",
        log_file=None,
        quiet=True,
        console=None,
    )
    await autocorrect.async_autocorrect(
        text=None,
        llm_config=llm_config,
        general_config=general_config,
    )
    mock_process_text.assert_not_called()
    mock_get_clipboard_text.assert_called_once()
