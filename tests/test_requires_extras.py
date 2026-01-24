"""Tests for @requires_extras decorator coverage on CLI commands."""

from __future__ import annotations

from agent_cli._extras import EXTRAS
from agent_cli.agents.assistant import assistant
from agent_cli.agents.autocorrect import autocorrect
from agent_cli.agents.chat import chat
from agent_cli.agents.memory.add import add
from agent_cli.agents.memory.proxy import proxy
from agent_cli.agents.rag_proxy import rag_proxy
from agent_cli.agents.transcribe import transcribe
from agent_cli.agents.transcribe_daemon import transcribe_daemon
from agent_cli.agents.voice_edit import voice_edit
from agent_cli.core.deps import check_extra_installed, requires_extras


class TestRequiresExtrasDecorator:
    """Test the requires_extras decorator functionality."""

    def test_decorator_stores_extras_on_function(self) -> None:
        """The decorator should store required extras on the function."""

        @requires_extras("audio", "llm")
        def sample_command() -> str:
            return "success"

        assert hasattr(sample_command, "_required_extras")
        assert sample_command._required_extras == ("audio", "llm")

    def test_check_extra_installed_unknown_extra(self) -> None:
        """Unknown extras should return True (assume OK)."""
        assert check_extra_installed("nonexistent-extra") is True


class TestCommandDecoratorCoverage:
    """Test that all commands that use optional dependencies have decorators."""

    def test_transcribe_has_audio_decorator(self) -> None:
        """Transcribe command should require audio extra."""
        assert hasattr(transcribe, "_required_extras")
        assert "audio" in transcribe._required_extras

    def test_transcribe_daemon_has_audio_and_vad_decorator(self) -> None:
        """transcribe-daemon command should require audio and vad extras."""
        assert hasattr(transcribe_daemon, "_required_extras")
        assert "audio" in transcribe_daemon._required_extras
        assert "vad" in transcribe_daemon._required_extras

    def test_chat_has_audio_and_llm_decorator(self) -> None:
        """Chat command should require audio and llm extras."""
        assert hasattr(chat, "_required_extras")
        assert "audio" in chat._required_extras
        assert "llm" in chat._required_extras

    def test_assistant_has_required_decorators(self) -> None:
        """Assistant command should require audio, llm, and wyoming extras."""
        assert hasattr(assistant, "_required_extras")
        assert "audio" in assistant._required_extras
        assert "llm" in assistant._required_extras
        assert "wyoming" in assistant._required_extras

    def test_voice_edit_has_audio_and_llm_decorator(self) -> None:
        """voice-edit command should require audio and llm extras."""
        assert hasattr(voice_edit, "_required_extras")
        assert "audio" in voice_edit._required_extras
        assert "llm" in voice_edit._required_extras

    def test_autocorrect_has_llm_decorator(self) -> None:
        """Autocorrect command should require llm extra."""
        assert hasattr(autocorrect, "_required_extras")
        assert "llm" in autocorrect._required_extras

    def test_rag_proxy_has_rag_decorator(self) -> None:
        """rag-proxy command should require rag extra."""
        assert hasattr(rag_proxy, "_required_extras")
        assert "rag" in rag_proxy._required_extras

    def test_memory_proxy_has_memory_decorator(self) -> None:
        """Memory proxy command should require memory extra."""
        assert hasattr(proxy, "_required_extras")
        assert "memory" in proxy._required_extras

    def test_memory_add_has_memory_decorator(self) -> None:
        """Memory add command should require memory extra."""
        assert hasattr(add, "_required_extras")
        assert "memory" in add._required_extras


class TestExtrasMetadata:
    """Test the _extras.py metadata is properly structured."""

    def test_extras_dict_structure(self) -> None:
        """EXTRAS dict should have proper structure."""
        assert isinstance(EXTRAS, dict)
        for name, value in EXTRAS.items():
            assert isinstance(name, str)
            assert isinstance(value, tuple)
            assert len(value) == 2
            desc, packages = value
            assert isinstance(desc, str)
            assert isinstance(packages, list)
            assert all(isinstance(pkg, str) for pkg in packages)

    def test_essential_extras_present(self) -> None:
        """Essential extras should be defined."""
        essential = ["audio", "wyoming", "openai", "gemini", "llm", "rag", "memory", "vad"]
        for extra in essential:
            assert extra in EXTRAS, f"Missing essential extra: {extra}"
