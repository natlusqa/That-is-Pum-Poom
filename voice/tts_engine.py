"""Piper TTS wrapper for text-to-speech synthesis."""

from __future__ import annotations

import asyncio
import io
import wave
from pathlib import Path
from typing import Optional

import structlog
from piper import PiperVoice, SynthesisConfig

logger = structlog.get_logger(__name__)

# Default Russian male voice (denis)
DEFAULT_VOICE = "ru_RU-denis-medium"
VOICE_CACHE_DIR = Path.home() / ".local" / "share" / "piper" / "voices"


class PiperTTS:
    """Text-to-speech using Piper with Russian male voice."""

    def __init__(
        self,
        voice_id: str = DEFAULT_VOICE,
        voice_dir: Optional[Path] = None,
        speed: float = 1.0,
        sample_rate: int = 22050,
        use_cuda: bool = False,
    ) -> None:
        """
        Args:
            voice_id: Voice model ID (e.g. ru_RU-denis-medium)
            voice_dir: Directory containing voice .onnx files
            speed: Speech speed (1.0 = normal, >1 = faster, <1 = slower)
            sample_rate: Output sample rate (22050 typical for Piper)
            use_cuda: Use GPU for inference
        """
        self.voice_id = voice_id
        self.voice_dir = voice_dir or VOICE_CACHE_DIR
        self.speed = speed
        self.sample_rate = sample_rate
        self.use_cuda = use_cuda
        self._voice: Optional[PiperVoice] = None

    def _resolve_voice_path(self) -> Path:
        """Resolve path to voice .onnx file."""
        candidates = [
            self.voice_dir / self.voice_id / f"{self.voice_id}.onnx",
            self.voice_dir / f"{self.voice_id}.onnx",
            Path(self.voice_id),  # Allow absolute path
        ]
        for p in candidates:
            if p.exists():
                return p
        # Return expected path for download (piper may auto-download)
        return self.voice_dir / self.voice_id / f"{self.voice_id}.onnx"

    def initialize(self) -> None:
        """Load the Piper voice model. Call before synthesize()."""
        if self._voice is not None:
            logger.warning("Piper voice already initialized")
            return

        model_path = self.voice_dir / self.voice_id / f"{self.voice_id}.onnx"
        if not model_path.exists():
            model_path = self.voice_dir / f"{self.voice_id}.onnx"
        if not model_path.exists():
            model_path = Path(self.voice_id) if Path(self.voice_id).exists() else None

        if model_path and Path(model_path).exists():
            path_str = str(model_path)
        else:
            path_str = str(self.voice_dir / self.voice_id / f"{self.voice_id}.onnx")
            if not Path(path_str).exists():
                raise FileNotFoundError(
                    f"Piper voice '{self.voice_id}' not found at {path_str}. "
                    f"Download with: python -m piper.download_voices {self.voice_id}"
                )

        logger.info(
            "loading_piper_voice",
            voice_id=self.voice_id,
            path=path_str,
            use_cuda=self.use_cuda,
        )

        self._voice = PiperVoice.load(path_str, use_cuda=self.use_cuda)
        logger.info("piper_voice_loaded")

    def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to audio bytes (WAV format).

        Args:
            text: Text to synthesize

        Returns:
            WAV audio as bytes
        """
        if self._voice is None:
            raise RuntimeError("PiperTTS not initialized. Call initialize() first.")

        if not text.strip():
            logger.warning("empty_text_synthesis")
            return b""

        syn_config = SynthesisConfig(
            length_scale=1.0 / self.speed if self.speed > 0 else 1.0,
            noise_scale=0.667,
            noise_w_scale=0.8,
        )

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_out:
            # Piper synthesize returns iterator of AudioChunk
            first_chunk = True
            for chunk in self._voice.synthesize(text.strip(), syn_config=syn_config):
                if first_chunk:
                    wav_out.setnchannels(chunk.num_channels)
                    wav_out.setsampwidth(chunk.sample_width)
                    wav_out.setframerate(chunk.sample_rate)
                    first_chunk = False
                wav_out.writeframes(chunk.audio_int16_bytes)

        result = buffer.getvalue()
        logger.debug("synthesis_complete", text_length=len(text), audio_bytes=len(result))
        return result

    async def synthesize_async(self, text: str) -> bytes:
        """Async wrapper for synthesize (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.synthesize, text)
