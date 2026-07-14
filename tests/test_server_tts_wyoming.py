"""Tests for the Wyoming TTS server handler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wyoming.info import Info
from wyoming.tts import Synthesize, SynthesizeVoice

from agent_cli.server.tts.wyoming_handler import WyomingTTSHandler, _tts_voice


def _handler(registry: MagicMock) -> WyomingTTSHandler:
    return WyomingTTSHandler(registry, MagicMock(), MagicMock())


@pytest.mark.parametrize(
    ("name", "language"),
    [
        ("af_heart", "en-US"),
        ("bm_george", "en-GB"),
        ("ef_dora", "es"),
        ("ff_siwis", "fr"),
        ("hf_alpha", "hi"),
        ("if_sara", "it"),
        ("jf_alpha", "ja"),
        ("pf_dora", "pt-BR"),
        ("zf_xiaobei", "zh"),
    ],
)
def test_kokoro_voice_language_tags(name: str, language: str) -> None:
    """Kokoro voice prefixes should map to language tags, not ISO codes."""
    assert _tts_voice(name, "kokoro").languages == [language]


@pytest.mark.parametrize(
    "model_name",
    ["kokoro", "/models/kokoro-v1_0.pth", "kokoro-v1_0", "custom-model"],
)
def test_kokoro_model_name_advertises_default_voice(model_name: str) -> None:
    """Kokoro model identifiers should not be advertised as voice names."""
    voice = _tts_voice(model_name, "kokoro")

    assert voice.name == "af_heart"
    assert voice.description == "Kokoro TTS af_heart"
    assert voice.languages == ["en-US"]


@pytest.mark.asyncio
@pytest.mark.parametrize("supports_streaming", [True, False])
async def test_synthesize_passes_voice_name(supports_streaming: bool) -> None:
    """Wyoming voice objects should be reduced to the selected voice name."""
    manager = MagicMock(supports_streaming=supports_streaming)
    registry = MagicMock()
    registry.get_manager.return_value = manager
    handler = _handler(registry)
    synthesize_streaming = AsyncMock()
    synthesize_complete = AsyncMock()
    event = Synthesize(
        text="Hello",
        voice=SynthesizeVoice(name="bm_george", speaker="speaker-1"),
    ).event()

    with (
        patch.object(handler, "_synthesize_streaming", synthesize_streaming),
        patch.object(handler, "_synthesize_complete", synthesize_complete),
    ):
        assert await handler.handle_event(event) is False

    method = synthesize_streaming if supports_streaming else synthesize_complete
    method.assert_awaited_once_with(manager, "Hello", "bm_george")


@pytest.mark.asyncio
async def test_describe_uses_backend_voice_metadata() -> None:
    """Kokoro voices should advertise real languages and Kokoro attribution."""
    registry = MagicMock()
    registry.list_status.return_value = [
        SimpleNamespace(name="af_heart"),
        SimpleNamespace(name="bm_george"),
        SimpleNamespace(name="en_US-lessac-medium"),
    ]
    registry.get_manager.side_effect = [
        SimpleNamespace(backend_type="kokoro"),
        SimpleNamespace(backend_type="kokoro"),
        SimpleNamespace(backend_type="piper"),
    ]
    handler = _handler(registry)
    write_event = AsyncMock()

    with patch.object(handler, "write_event", write_event):
        assert await handler._handle_describe() is True

    await_args = write_event.await_args
    assert await_args is not None
    event = await_args.args[0]
    voices = Info.from_event(event).tts[0].voices
    assert voices is not None
    assert [(voice.name, voice.languages) for voice in voices] == [
        ("af_heart", ["en-US"]),
        ("bm_george", ["en-GB"]),
        ("en_US-lessac-medium", ["en"]),
    ]
    assert voices[0].description == "Kokoro TTS af_heart"
    assert voices[0].attribution.name == "Kokoro"
    assert voices[2].description == "Piper TTS en_US-lessac-medium"
    assert voices[2].attribution.name == "Piper"
