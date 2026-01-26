"""Tests for the autocorrect agent."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from agent_cli import config
from agent_cli.agents import autocorrect
from agent_cli.constants import DEFAULT_OPENAI_MODEL


def test_system_prompt_and_instructions():
    """Test that the system prompt and instructions are properly defined."""
    assert autocorrect.SYSTEM_PROMPT
    assert "text correction tool" in autocorrect.SYSTEM_PROMPT.lower()
    assert "correct" in autocorrect.SYSTEM_PROMPT.lower()

    assert autocorrect.AGENT_INSTRUCTIONS
    assert "grammar" in autocorrect.AGENT_INSTRUCTIONS.lower()
    assert "spelling" in autocorrect.AGENT_INSTRUCTIONS.lower()


def test_display_result_quiet_mode():
    """Test the _display_result function in quiet mode with real output."""
    # Test normal correction
    with patch("pyperclip.copy") as mock_copy:
        output = io.StringIO()
        with redirect_stdout(output):
            autocorrect._display_result(
                "Hello world!",
                "hello world",
                0.1,
                simple_output=True,
            )

        assert output.getvalue().strip() == "Hello world!"
        mock_copy.assert_called_once_with("Hello world!")


def test_display_result_no_correction_needed():
    """Test the _display_result function when no correction is needed."""
    with patch("pyperclip.copy") as mock_copy:
        output = io.StringIO()
        with redirect_stdout(output):
            autocorrect._display_result(
                "Hello world!",
                "Hello world!",
                0.1,
                simple_output=True,
            )

        assert output.getvalue().strip() == "✅ No correction needed."
        mock_copy.assert_called_once_with("Hello world!")


def test_display_result_verbose_mode():
    """Test the _display_result function in verbose mode with real console output."""
    mock_console = Console(file=io.StringIO(), width=80)
    with (
        patch("agent_cli.core.utils.console", mock_console),
        patch("pyperclip.copy") as mock_copy,
    ):
        autocorrect._display_result(
            "Hello world!",
            "hello world",
            0.25,
            simple_output=False,
        )

        output = mock_console.file.getvalue()
        assert "Hello world!" in output
        assert "Corrected Text" in output
        assert "Success!" in output
        mock_copy.assert_called_once_with("Hello world!")


def test_display_original_text():
    """Test the display_original_text function."""
    mock_console = Console(file=io.StringIO(), width=80)
    with patch("agent_cli.core.utils.console", mock_console):
        autocorrect._display_original_text("Test text here", quiet=False)
        output = mock_console.file.getvalue()
        assert "Test text here" in output
        assert "Original Text" in output


def test_display_original_text_none_console():
    """Test display_original_text with None console (should not crash)."""
    mock_console = Console(file=io.StringIO(), width=80)
    with patch("agent_cli.core.utils.console", mock_console):
        # This should not raise an exception or print anything
        autocorrect._display_original_text("Test text", quiet=True)
        assert mock_console.file.getvalue() == ""


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect.create_llm_agent")
async def test_process_text_integration(mock_create_llm_agent: MagicMock) -> None:
    """Test process_text with a more realistic mock setup."""
    # Create a mock agent that behaves more like the real thing
    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "This is corrected text."
    mock_agent.run = AsyncMock(return_value=mock_result)
    mock_create_llm_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test-model", llm_ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    # Test the function
    result, elapsed = await autocorrect._process_text(
        "this is text",
        provider_cfg,
        ollama_cfg,
        openai_llm_cfg,
        gemini_llm_cfg,
    )

    # Verify the result
    assert result == "This is corrected text."
    assert isinstance(elapsed, float)
    assert elapsed >= 0

    # Verify the agent was called correctly
    mock_create_llm_agent.assert_called_once_with(
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_llm_cfg,
        gemini_cfg=gemini_llm_cfg,
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    expected_input = "\n<text-to-correct>\nthis is text\n</text-to-correct>\n\nPlease correct any grammar, spelling, or punctuation errors in the text above.\n"
    mock_agent.run.assert_called_once_with(expected_input)


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect.create_llm_agent")
@patch("agent_cli.agents.autocorrect.get_clipboard_text")
async def test_autocorrect_command_with_text(
    mock_get_clipboard: MagicMock,
    mock_create_llm_agent: MagicMock,
) -> None:
    """Test the autocorrect command with text provided as an argument."""
    # Setup
    mock_get_clipboard.return_value = "from clipboard"
    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "Corrected text."
    mock_agent.run = AsyncMock(return_value=mock_result)
    mock_create_llm_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model="gemma3:4b",
        llm_ollama_host="http://localhost:11434",
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    general_cfg = config.General(
        log_level="WARNING",
        log_file=None,
        quiet=True,
        clipboard=True,
    )

    with patch("pyperclip.copy"):
        await autocorrect._async_autocorrect(
            text="input text",
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            general_cfg=general_cfg,
        )

    # Assertions
    mock_get_clipboard.assert_not_called()
    mock_create_llm_agent.assert_called_once_with(
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_llm_cfg,
        gemini_cfg=gemini_llm_cfg,
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    expected_input = "\n<text-to-correct>\ninput text\n</text-to-correct>\n\nPlease correct any grammar, spelling, or punctuation errors in the text above.\n"
    mock_agent.run.assert_called_once_with(expected_input)


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect.create_llm_agent")
@patch("agent_cli.agents.autocorrect.get_clipboard_text")
async def test_autocorrect_command_from_clipboard(
    mock_get_clipboard: MagicMock,
    mock_create_llm_agent: MagicMock,
) -> None:
    """Test the autocorrect command reading from the clipboard."""
    # Setup
    mock_get_clipboard.return_value = "clipboard text"
    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "Corrected clipboard text."
    mock_agent.run = AsyncMock(return_value=mock_result)
    mock_create_llm_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model="gemma3:4b",
        llm_ollama_host="http://localhost:11434",
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    general_cfg = config.General(
        log_level="WARNING",
        log_file=None,
        quiet=True,
        clipboard=True,
    )

    with patch("pyperclip.copy"):
        await autocorrect._async_autocorrect(
            text=None,  # No text argument provided
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            general_cfg=general_cfg,
        )

    # Assertions
    mock_get_clipboard.assert_called_once_with(quiet=True)
    mock_create_llm_agent.assert_called_once_with(
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_llm_cfg,
        gemini_cfg=gemini_llm_cfg,
        system_prompt=autocorrect.SYSTEM_PROMPT,
        instructions=autocorrect.AGENT_INSTRUCTIONS,
    )
    expected_input = "\n<text-to-correct>\nclipboard text\n</text-to-correct>\n\nPlease correct any grammar, spelling, or punctuation errors in the text above.\n"
    mock_agent.run.assert_called_once_with(expected_input)


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect._process_text", new_callable=AsyncMock)
@patch("agent_cli.agents.autocorrect.get_clipboard_text", return_value=None)
async def test_async_autocorrect_no_text(
    mock_get_clipboard_text: MagicMock,
    mock_process_text: AsyncMock,
) -> None:
    """Test the async_autocorrect function when no text is provided."""
    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    general_cfg = config.General(
        log_level="WARNING",
        log_file=None,
        quiet=True,
        clipboard=True,
    )
    await autocorrect._async_autocorrect(
        text=None,
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_llm_cfg=openai_llm_cfg,
        gemini_llm_cfg=gemini_llm_cfg,
        general_cfg=general_cfg,
    )
    mock_process_text.assert_not_called()
    mock_get_clipboard_text.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents.autocorrect._process_text", side_effect=Exception("Test error"))
async def test_async_autocorrect_error(mock_process_text: AsyncMock):
    """Test the async_autocorrect function when an error occurs."""
    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    general_cfg = config.General(
        log_level="WARNING",
        log_file=None,
        quiet=False,
        clipboard=True,
    )
    with pytest.raises(SystemExit) as excinfo:
        await autocorrect._async_autocorrect(
            text="test text",
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            general_cfg=general_cfg,
        )
    assert excinfo.value.code == 1
    mock_process_text.assert_called_once()
