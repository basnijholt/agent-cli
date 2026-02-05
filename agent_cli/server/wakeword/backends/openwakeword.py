"""OpenWakeWord backend for wakeword detection."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_cli.server.wakeword.backends.base import (
    BackendConfig,
    DetectionResult,
    ModelInfo,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

logger = logging.getLogger(__name__)

# Wakeword detection uses 16kHz audio
WAKEWORD_SAMPLE_RATE = 16000


def _get_phrase(name: str) -> str:
    """Convert model name to human-readable phrase."""
    phrase = name.lower().strip().replace("_", " ")
    return " ".join(w.capitalize() for w in phrase.split())


@dataclass
class DetectorState:
    """State for a single wake word detector."""

    id: str
    oww_model: OpenWakeWord
    triggers_left: int
    is_detected: bool = False
    last_triggered: float | None = None


class OpenWakeWordBackend:
    """OpenWakeWord backend for wake word detection.

    This backend uses the pyopen-wakeword library for detection.
    Unlike ASR/TTS models, wakeword models are lightweight and CPU-based.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend.

        Args:
            config: Backend configuration.

        """
        self._config = config
        self._features: OpenWakeWordFeatures | None = None
        self._detector: DetectorState | None = None
        self._device: str | None = None
        self._custom_models: dict[str, Path] = {}
        self._audio_timestamp: int = 0

        # Load custom models from directory if specified
        if config.custom_model_dir:
            self._load_custom_models(config.custom_model_dir)

    def _load_custom_models(self, custom_dir: Path) -> None:
        """Load custom wake word models from a directory."""
        name_version = re.compile(r"^([^_]+)_v[0-9.]+$")

        for model_path in custom_dir.glob("*.tflite"):
            model_id = model_path.stem
            name_match = name_version.match(model_id)
            if name_match:
                model_id = name_match.group(1)

            if model_id not in self._custom_models:
                self._custom_models[model_id] = model_path
                logger.debug("Found custom model %s at %s", model_id, model_path)

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._detector is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        return self._device

    async def load(self) -> float:
        """Load the wake word model.

        Returns:
            Load duration in seconds.

        """
        start_time = time.time()

        def _load() -> None:
            from pyopen_wakeword import (  # noqa: PLC0415
                Model,
                OpenWakeWord,
                OpenWakeWordFeatures,
            )

            self._features = OpenWakeWordFeatures.from_builtin()

            model_name = self._config.model_name
            oww_model: OpenWakeWord | None = None

            # Check if it's a custom model
            if model_name in self._custom_models:
                oww_model = OpenWakeWord.from_model(self._custom_models[model_name])
            else:
                # Try as a builtin model
                try:
                    model = Model(model_name)
                    oww_model = OpenWakeWord.from_builtin(model)
                except ValueError:
                    # Try common variations
                    model_variations = [
                        model_name,
                        model_name.lower(),
                        model_name.replace("-", "_"),
                        model_name.replace("_", "-"),
                    ]
                    for variation in model_variations:
                        try:
                            model = Model(variation)
                            oww_model = OpenWakeWord.from_builtin(model)
                            break
                        except ValueError:
                            continue

            if oww_model is None:
                msg = f"Could not load wake word model: {model_name}"
                raise ValueError(msg)

            self._detector = DetectorState(
                id=model_name,
                oww_model=oww_model,
                triggers_left=self._config.trigger_level,
            )
            self._device = "cpu"

        await asyncio.get_event_loop().run_in_executor(None, _load)
        load_duration = time.time() - start_time

        logger.info(
            "Loaded wakeword model %s in %.2fs",
            self._config.model_name,
            load_duration,
        )

        return load_duration

    async def unload(self) -> None:
        """Unload the model and free memory."""
        if self._detector is not None:
            self._detector = None
            self._features = None
            self._device = None
            self._audio_timestamp = 0
            logger.info("Unloaded wakeword model %s", self._config.model_name)

    def reset(self) -> None:
        """Reset the detector state for a new audio stream."""
        self._audio_timestamp = 0
        if self._features is not None:
            self._features.reset()
        if self._detector is not None:
            self._detector.is_detected = False
            self._detector.triggers_left = self._config.trigger_level
            self._detector.last_triggered = None
            self._detector.oww_model.reset()

    def process_audio(self, audio_chunk: bytes) -> list[DetectionResult]:
        """Process an audio chunk and return any detections.

        Args:
            audio_chunk: Raw PCM audio bytes (16-bit, 16kHz, mono).

        Returns:
            List of detections found in this chunk.

        """
        if self._features is None or self._detector is None:
            return []

        detections: list[DetectionResult] = []

        # Calculate chunk duration in milliseconds
        # 16-bit = 2 bytes per sample, 16kHz sample rate
        chunk_ms = len(audio_chunk) // 2 * 1000 // WAKEWORD_SAMPLE_RATE

        for features in self._features.process_streaming(audio_chunk):
            detector = self._detector

            # Check refractory period
            skip_detector = (detector.last_triggered is not None) and (
                (time.monotonic() - detector.last_triggered) < self._config.refractory_seconds
            )

            for prob in detector.oww_model.process_streaming(features):
                if skip_detector:
                    continue

                if prob <= self._config.threshold:
                    # Reset trigger count on low probability
                    detector.triggers_left = self._config.trigger_level
                    continue

                detector.triggers_left -= 1
                if detector.triggers_left > 0:
                    continue

                # Detection!
                detector.is_detected = True
                detector.last_triggered = time.monotonic()
                detector.triggers_left = self._config.trigger_level

                detections.append(
                    DetectionResult(
                        name=detector.id,
                        timestamp=self._audio_timestamp,
                        probability=prob,
                    ),
                )
                logger.debug(
                    "Detected %s at %dms (prob=%.3f)",
                    detector.id,
                    self._audio_timestamp,
                    prob,
                )

        self._audio_timestamp += chunk_ms
        return detections

    def get_available_models(self) -> list[ModelInfo]:
        """Get list of available wake word models."""
        from pyopen_wakeword import Model  # noqa: PLC0415

        # Add builtin models
        models = [
            ModelInfo(
                name=model.value,
                phrase=_get_phrase(model.value),
                languages=["en"],
                is_builtin=True,
            )
            for model in Model
        ]

        # Add custom models
        models.extend(
            ModelInfo(
                name=custom_name,
                phrase=_get_phrase(custom_name),
                languages=[],
                is_builtin=False,
            )
            for custom_name in self._custom_models
        )

        return models
