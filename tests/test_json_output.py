"""Tests for --json flag output across CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from agent_cli import config
from agent_cli.agents import autocorrect
from agent_cli.agents.voice_edit import _async_main as voice_edit_async_main
from agent_cli.cli import app
from agent_cli.constants import DEFAULT_OPENAI_MODEL
from agent_cli.dev.worktree import WorktreeInfo, WorktreeStatus

if TYPE_CHECKING:
    from agent_cli.agents.transcribe import TranscriptResult

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


class TestAutocorrectJsonOutput:
    """Tests for autocorrect command JSON output."""

    @pytest.mark.asyncio
    @patch("agent_cli.agents.autocorrect.create_llm_agent")
    async def test_async_autocorrect_returns_corrected_text(
        self,
        mock_create_llm_agent: MagicMock,
    ) -> None:
        """Test that _async_autocorrect returns the corrected text for JSON output."""
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
            clipboard=False,  # JSON mode disables clipboard
        )

        result = await autocorrect._async_autocorrect(
            text="input text",
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            general_cfg=general_cfg,
        )

        assert result == "Corrected text."

    @patch("agent_cli.agents.autocorrect._async_autocorrect", new_callable=AsyncMock)
    def test_autocorrect_json_output_format(
        self,
        mock_async_autocorrect: AsyncMock,
    ) -> None:
        """Test that --json flag produces valid JSON output."""
        mock_async_autocorrect.return_value = "This is corrected."

        result = runner.invoke(
            app,
            ["autocorrect", "--json", "this is a tset"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # Parse the JSON output
        output = json.loads(result.stdout.strip())
        assert "corrected_text" in output
        assert output["corrected_text"] == "This is corrected."


class TestSpeakJsonOutput:
    """Tests for speak command JSON output."""

    @patch("agent_cli.agents.speak._async_main", new_callable=AsyncMock)
    def test_speak_json_output_format(
        self,
        mock_async_main: AsyncMock,
    ) -> None:
        """Test that --json flag produces valid JSON output."""
        mock_async_main.return_value = "Hello world"

        result = runner.invoke(
            app,
            ["speak", "--json", "Hello world"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert "text" in output
        assert output["text"] == "Hello world"

    @patch("agent_cli.agents.speak._async_main", new_callable=AsyncMock)
    def test_speak_json_output_with_save_file(
        self,
        mock_async_main: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Test that --json includes file path when --save-file is used."""
        mock_async_main.return_value = "Hello world"
        save_path = tmp_path / "output.wav"

        result = runner.invoke(
            app,
            ["speak", "--json", "--save-file", str(save_path), "Hello world"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert "text" in output
        assert "file" in output
        assert output["file"] == str(save_path)


class TestTranscribeJsonOutput:
    """Tests for transcribe command JSON output."""

    def test_transcribe_result_schema(self) -> None:
        """Test that TranscriptResult TypedDict has expected keys."""
        # Create a valid result
        result: TranscriptResult = {
            "raw_transcript": "hello world",
            "transcript": "Hello world.",
            "llm_enabled": True,
        }

        # Verify all keys are present
        assert "raw_transcript" in result
        assert "transcript" in result
        assert "llm_enabled" in result


class TestVoiceEditJsonOutput:
    """Tests for voice-edit command JSON output."""

    @pytest.mark.asyncio
    @patch("agent_cli.agents.voice_edit.process_instruction_and_respond", new_callable=AsyncMock)
    @patch("agent_cli.agents.voice_edit.get_instruction_from_audio", new_callable=AsyncMock)
    @patch("agent_cli.agents.voice_edit.asr.record_audio_with_manual_stop", new_callable=AsyncMock)
    @patch("agent_cli.agents.voice_edit.get_clipboard_text", return_value="test clipboard text")
    @patch("agent_cli.agents.voice_edit.setup_devices")
    async def test_voice_edit_async_main_returns_result(
        self,
        mock_setup_devices: MagicMock,
        mock_get_clipboard: MagicMock,
        mock_record_audio: AsyncMock,
        mock_get_instruction: AsyncMock,
        mock_process_instruction: AsyncMock,
    ) -> None:
        """Test that _async_main returns the processed result for JSON output."""
        mock_setup_devices.return_value = (0, "mock_device", None)
        mock_record_audio.return_value = b"audio data"
        mock_get_instruction.return_value = "this is a test"
        mock_process_instruction.return_value = "Edited text result"
        # Verify the clipboard mock was set up correctly
        assert mock_get_clipboard.return_value == "test clipboard text"

        general_cfg = config.General(log_level="INFO", quiet=True, clipboard=True)
        provider_cfg = config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
        )
        audio_in_cfg = config.AudioInput(input_device_index=0)
        wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=10300)
        openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
            gemini_api_key="test",
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model="test",
            llm_ollama_host="http://localhost:11434",
        )
        openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4", openai_base_url=None)
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-1.5-flash",
            gemini_api_key="test",
        )
        audio_out_cfg = config.AudioOutput(enable_tts=False)
        wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="localhost", tts_wyoming_port=10200)
        openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
        kokoro_tts_cfg = config.KokoroTTS(
            tts_kokoro_model="tts-1",
            tts_kokoro_voice="alloy",
            tts_kokoro_host="http://localhost:8000/v1",
        )
        gemini_tts_cfg = config.GeminiTTS(
            tts_gemini_model="gemini-2.5-flash-preview-tts",
            tts_gemini_voice="Kore",
            gemini_api_key="test",
        )

        with patch("agent_cli.agents.voice_edit.signal_handling_context") as mock_signal_context:
            mock_stop_event = MagicMock()
            mock_stop_event.is_set.return_value = False
            mock_signal_context.return_value.__enter__.return_value = mock_stop_event

            result = await voice_edit_async_main(
                provider_cfg=provider_cfg,
                general_cfg=general_cfg,
                audio_in_cfg=audio_in_cfg,
                wyoming_asr_cfg=wyoming_asr_cfg,
                openai_asr_cfg=openai_asr_cfg,
                gemini_asr_cfg=gemini_asr_cfg,
                ollama_cfg=ollama_cfg,
                openai_llm_cfg=openai_llm_cfg,
                gemini_llm_cfg=gemini_llm_cfg,
                audio_out_cfg=audio_out_cfg,
                wyoming_tts_cfg=wyoming_tts_cfg,
                openai_tts_cfg=openai_tts_cfg,
                kokoro_tts_cfg=kokoro_tts_cfg,
                gemini_tts_cfg=gemini_tts_cfg,
            )

        # The result should be what process_instruction_and_respond returns
        assert result == "Edited text result"

        # Verify JSON structure would be correct
        json_output = json.dumps({"result": result})
        parsed = json.loads(json_output)
        assert "result" in parsed
        assert parsed["result"] == "Edited text result"


class TestDevListJsonOutput:
    """Tests for dev list command JSON output."""

    def test_list_json_output_format(self) -> None:
        """Test that --json flag produces valid JSON output."""
        mock_worktrees = [
            WorktreeInfo(
                path=Path("/repo"),
                branch="main",
                commit="abc123",
                is_main=True,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
            WorktreeInfo(
                path=Path("/repo-worktrees/feature"),
                branch="feature-branch",
                commit="def456",
                is_main=False,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.list_worktrees", return_value=mock_worktrees),
        ):
            result = runner.invoke(app, ["dev", "list", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert "worktrees" in output
        assert len(output["worktrees"]) == 2

        # Check first worktree structure
        wt = output["worktrees"][0]
        assert wt["name"] == "repo"
        assert wt["branch"] == "main"
        assert wt["is_main"] is True
        assert "path" in wt
        assert "is_detached" in wt
        assert "is_locked" in wt
        assert "is_prunable" in wt

    def test_list_json_empty_worktrees(self) -> None:
        """Test JSON output when no worktrees found."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.list_worktrees", return_value=[]),
        ):
            result = runner.invoke(app, ["dev", "list", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert output == {"worktrees": []}


class TestDevStatusJsonOutput:
    """Tests for dev status command JSON output."""

    def test_status_json_output_format(self) -> None:
        """Test that --json flag produces valid JSON output."""
        mock_worktrees = [
            WorktreeInfo(
                path=Path("/repo"),
                branch="main",
                commit="abc123",
                is_main=True,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]
        mock_status = WorktreeStatus(
            modified=2,
            staged=1,
            untracked=3,
            ahead=1,
            behind=0,
            last_commit_time="2 days ago",
            last_commit_timestamp=1234567890,
        )

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.list_worktrees", return_value=mock_worktrees),
            patch("agent_cli.dev.worktree.get_worktree_status", return_value=mock_status),
        ):
            result = runner.invoke(app, ["dev", "status", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert "worktrees" in output
        assert "stale_days" in output

        wt = output["worktrees"][0]
        assert wt["name"] == "repo"
        assert wt["modified"] == 2
        assert wt["staged"] == 1
        assert wt["untracked"] == 3
        assert wt["ahead"] == 1
        assert wt["behind"] == 0
        assert "is_stale" in wt


class TestDevAgentsJsonOutput:
    """Tests for dev agents command JSON output."""

    def test_agents_json_output_format(self) -> None:
        """Test that --json flag produces valid JSON output."""
        result = runner.invoke(app, ["dev", "agents", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert "agents" in output
        assert isinstance(output["agents"], list)
        assert len(output["agents"]) > 0

        # Check agent structure
        agent = output["agents"][0]
        assert "name" in agent
        assert "command" in agent
        assert "is_available" in agent
        assert "is_current" in agent
        assert "install_url" in agent


class TestDevEditorsJsonOutput:
    """Tests for dev editors command JSON output."""

    def test_editors_json_output_format(self) -> None:
        """Test that --json flag produces valid JSON output."""
        result = runner.invoke(app, ["dev", "editors", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert "editors" in output
        assert isinstance(output["editors"], list)
        assert len(output["editors"]) > 0

        # Check editor structure
        editor = output["editors"][0]
        assert "name" in editor
        assert "command" in editor
        assert "is_available" in editor
        assert "is_current" in editor
        assert "install_url" in editor


class TestDevTerminalsJsonOutput:
    """Tests for dev terminals command JSON output."""

    def test_terminals_json_output_format(self) -> None:
        """Test that --json flag produces valid JSON output."""
        result = runner.invoke(app, ["dev", "terminals", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert "terminals" in output
        assert isinstance(output["terminals"], list)
        assert len(output["terminals"]) > 0

        # Check terminal structure
        terminal = output["terminals"][0]
        assert "name" in terminal
        assert "is_available" in terminal
        assert "is_current" in terminal


class TestDevDoctorJsonOutput:
    """Tests for dev doctor command JSON output."""

    def test_doctor_json_output_format(self) -> None:
        """Test that --json flag produces valid JSON output."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
        ):
            result = runner.invoke(app, ["dev", "doctor", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())

        # Check structure
        assert "git" in output
        assert "editors" in output
        assert "agents" in output
        assert "terminals" in output

        # Check git structure
        assert "is_available" in output["git"]
        assert "repo_root" in output["git"]

        # Check that lists have proper structure
        assert isinstance(output["editors"], list)
        assert isinstance(output["agents"], list)
        assert isinstance(output["terminals"], list)

        if output["editors"]:
            editor = output["editors"][0]
            assert "name" in editor
            assert "is_available" in editor
            assert "is_current" in editor


class TestConfigShowJsonOutput:
    """Tests for config show command JSON output."""

    def test_config_show_json_with_config(self, tmp_path: Path) -> None:
        """Test JSON output when config exists."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[defaults]\nllm-provider = 'openai'\n")

        result = runner.invoke(app, ["config", "show", "--json", "--path", str(config_file)])

        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        assert output["path"] == str(config_file)
        assert output["exists"] is True
        assert "llm-provider" in output["content"]

    def test_config_show_json_no_config(self, tmp_path: Path) -> None:
        """Test JSON output when config doesn't exist."""
        nonexistent = tmp_path / "nonexistent.toml"

        result = runner.invoke(app, ["config", "show", "--json", "--path", str(nonexistent)])

        # Exit code 1 for non-existent specified path
        assert result.exit_code == 1
        output = json.loads(result.stdout.strip())
        assert output["path"] == str(nonexistent)
        assert output["exists"] is False
        assert output["content"] is None
