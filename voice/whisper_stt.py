"""Whisper STT wrapper using faster-whisper with CTranslate2."""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Optional

import structlog
from faster_whisper import WhisperModel

logger = structlog.get_logger(__name__)


class WhisperSTT:
    """Speech-to-text using faster-whisper with CTranslate2."""

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "auto",
        compute_type: str = "float16",
        download_root: Optional[str] = None,
    ) -> None:
        """
        Args:
            model_size: Model size (tiny, base, small, medium, large-v3, etc.)
            device: Device for inference ("cpu", "cuda", "auto")
            compute_type: Compute type (float16, int8 for CPU)
            download_root: Optional directory for model cache
        """
        self.model_size = model_size
        detected = self._detect_device()
        self.device = device if device != "auto" else detected
        self.compute_type = self._resolve_compute_type(compute_type, detected)
        self.download_root = download_root
        self._model: Optional[WhisperModel] = None

    def _detect_device(self) -> str:
        """Detect CUDA availability for GPU support."""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    def _resolve_compute_type(self, compute_type: str, device: str) -> str:
        """Use int8 for CPU, float16 for CUDA by default."""
        if device == "cpu" and compute_type == "float16":
            return "int8"
        return compute_type

    def initialize(self) -> None:
        """Load the Whisper model. Call before transcribe()."""
        if self._model is not None:
            logger.warning("Whisper model already initialized")
            return

        logger.info(
            "loading_whisper_model",
            model_size=self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=self.download_root,
        )
        logger.info("whisper_model_loaded")

    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio bytes (WAV, MP3, etc.)

        Returns:
            Transcribed text. Empty string if no speech detected.
        """
        if self._model is None:
            raise RuntimeError("WhisperSTT not initialized. Call initialize() first.")

        buffer = BytesIO(audio_bytes)
        segments, info = self._model.transcribe(
            buffer,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 300,
                "speech_pad_ms": 100,
                "threshold": 0.5,
            },
        )

        text_parts = []
        for segment in segments:
            if segment.text.strip():
                text_parts.append(segment.text.strip())

        result = " ".join(text_parts) if text_parts else ""
        logger.debug(
            "transcription_complete",
            language=info.language,
            duration=info.duration,
            text_length=len(result),
        )
        return result

    async def transcribe_async(self, audio_bytes: bytes) -> str:
        """Async wrapper for transcribe (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.transcribe, audio_bytes)
