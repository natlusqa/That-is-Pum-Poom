"""Speaker verification using SpeechBrain ECAPA-TDNN."""

from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import structlog
import torch
import torchaudio

logger = structlog.get_logger(__name__)

DEFAULT_THRESHOLD = 0.75
EMBEDDINGS_DIR = Path.home() / ".korgan" / "voice" / "embeddings"
MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
TARGET_SAMPLE_RATE = 16000


class SpeakerRecognition:
    """Speaker verification using ECAPA-TDNN embeddings and cosine similarity."""

    def __init__(
        self,
        similarity_threshold: float = DEFAULT_THRESHOLD,
        embeddings_dir: Optional[Path] = None,
        use_cuda: bool = True,
    ) -> None:
        """
        Args:
            similarity_threshold: Minimum cosine similarity for verification (0.0-1.0)
            embeddings_dir: Directory for secure embedding storage
            use_cuda: Use GPU for inference
        """
        self.similarity_threshold = similarity_threshold
        self.embeddings_dir = Path(embeddings_dir) if embeddings_dir else EMBEDDINGS_DIR
        self.use_cuda = use_cuda and torch.cuda.is_available()
        self._encoder = None
        self._enrolled_embedding: Optional[torch.Tensor] = None
        self._speaker_id: Optional[str] = None

    def initialize(self) -> None:
        """Load the ECAPA-TDNN model. Call before enroll/verify."""
        if self._encoder is not None:
            logger.warning("Speaker recognition model already initialized")
            return

        logger.info(
            "loading_speaker_model",
            source=MODEL_SOURCE,
            device="cuda" if self.use_cuda else "cpu",
        )

        from speechbrain.inference.speaker import EncoderClassifier

        run_opts = {"device": "cuda" if self.use_cuda else "cpu"}
        self._encoder = EncoderClassifier.from_hparams(
            source=MODEL_SOURCE,
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts=run_opts,
        )

        self.embeddings_dir.mkdir(parents=True, exist_ok=True)
        # Restrict directory permissions on Unix
        try:
            os.chmod(self.embeddings_dir, 0o700)
        except OSError:
            pass

        logger.info("speaker_model_loaded")

    def _audio_to_tensor(self, audio_bytes: bytes) -> torch.Tensor:
        """Load audio bytes to tensor, resampled to 16kHz mono."""
        buffer = io.BytesIO(audio_bytes)
        waveform, sample_rate = torchaudio.load(buffer)
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if sample_rate != TARGET_SAMPLE_RATE:
            resampler = torchaudio.transforms.Resample(sample_rate, TARGET_SAMPLE_RATE)
            waveform = resampler(waveform)
        return waveform

    def _extract_embedding(self, audio_bytes: bytes) -> torch.Tensor:
        """Extract speaker embedding from audio."""
        if self._encoder is None:
            raise RuntimeError(
                "SpeakerRecognition not initialized. Call initialize() first."
            )
        waveform = self._audio_to_tensor(audio_bytes)
        with torch.no_grad():
            embedding = self._encoder.encode_batch(waveform)
        return embedding.squeeze(0)

    def enroll(self, audio_samples: List[bytes], speaker_id: str = "default") -> None:
        """
        Enroll a speaker from multiple audio samples.

        Args:
            audio_samples: List of audio byte samples (WAV format)
            speaker_id: Identifier for the enrolled speaker
        """
        if self._encoder is None:
            raise RuntimeError(
                "SpeakerRecognition not initialized. Call initialize() first."
            )

        if not audio_samples:
            raise ValueError("At least one audio sample required for enrollment")

        embeddings = []
        for i, audio_bytes in enumerate(audio_samples):
            try:
                emb = self._extract_embedding(audio_bytes)
                embeddings.append(emb.cpu().numpy())
            except Exception as e:
                logger.warning("enroll_sample_failed", index=i, error=str(e))
                raise

        # Average embeddings for robust enrollment
        avg_embedding = np.mean(embeddings, axis=0)
        self._enrolled_embedding = torch.from_numpy(avg_embedding).float()
        self._speaker_id = speaker_id

        # Store securely (restricted permissions)
        storage_path = self.embeddings_dir / f"{speaker_id}.json"
        data = {
            "speaker_id": speaker_id,
            "embedding": avg_embedding.tolist(),
        }
        with open(storage_path, "w") as f:
            json.dump(data, f)
        try:
            os.chmod(storage_path, 0o600)
        except OSError:
            pass

        logger.info("speaker_enrolled", speaker_id=speaker_id, samples=len(audio_samples))

    def load_enrollment(self, speaker_id: str) -> None:
        """Load enrolled speaker from storage."""
        storage_path = self.embeddings_dir / f"{speaker_id}.json"
        if not storage_path.exists():
            raise FileNotFoundError(f"No enrollment found for speaker '{speaker_id}'")
        with open(storage_path) as f:
            data = json.load(f)
        self._enrolled_embedding = torch.tensor(data["embedding"], dtype=torch.float32)
        self._speaker_id = data["speaker_id"]
        logger.debug("enrollment_loaded", speaker_id=speaker_id)

    def verify(self, audio: bytes) -> Tuple[bool, float]:
        """
        Verify if audio matches the enrolled speaker.

        Args:
            audio: Audio bytes (WAV format) to verify

        Returns:
            Tuple of (match: bool, similarity_score: float)
        """
        if self._encoder is None or self._enrolled_embedding is None:
            raise RuntimeError(
                "SpeakerRecognition not initialized or no speaker enrolled. "
                "Call initialize() and enroll() first."
            )

        test_embedding = self._extract_embedding(audio)
        enrolled = self._enrolled_embedding
        if self.use_cuda:
            enrolled = enrolled.to(test_embedding.device)

        # Cosine similarity (SpeechBrain uses similarity, higher = more similar)
        similarity = torch.nn.functional.cosine_similarity(
            test_embedding.unsqueeze(0),
            enrolled.unsqueeze(0),
        ).item()

        match = similarity >= self.similarity_threshold
        logger.debug(
            "verification_result",
            match=match,
            similarity=round(similarity, 4),
            threshold=self.similarity_threshold,
        )
        return match, float(similarity)

    async def enroll_async(
        self, audio_samples: List[bytes], speaker_id: str = "default"
    ) -> None:
        """Async wrapper for enroll."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self.enroll(audio_samples, speaker_id)
        )

    async def verify_async(self, audio: bytes) -> Tuple[bool, float]:
        """Async wrapper for verify."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.verify, audio)
