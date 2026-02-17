"""FastAPI service for KORGAN AI Voice System (port 8001)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional

import structlog
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from voice.speaker_recognition import SpeakerRecognition
from voice.tts_engine import PiperTTS
from voice.whisper_stt import WhisperSTT

logger = structlog.get_logger(__name__)

# Global engine instances (initialized in lifespan)
stt_engine: Optional[WhisperSTT] = None
tts_engine: Optional[PiperTTS] = None
speaker_engine: Optional[SpeakerRecognition] = None


# --- Pydantic Models ---


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="ok", description="Service status")
    stt_ready: bool = Field(description="STT engine ready")
    tts_ready: bool = Field(description="TTS engine ready")
    speaker_ready: bool = Field(description="Speaker recognition ready")


class STTResponse(BaseModel):
    """Speech-to-text response."""

    text: str = Field(description="Transcribed text")


class TTSRequest(BaseModel):
    """Text-to-speech request (alternative to form)."""

    text: str = Field(..., min_length=1, max_length=10000)


class VerifySpeakerResponse(BaseModel):
    """Speaker verification response."""

    match: bool = Field(description="Whether the speaker matches")
    similarity: float = Field(ge=0.0, le=1.0, description="Cosine similarity score")


# --- Lifespan ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize engines on startup, cleanup on shutdown."""
    global stt_engine, tts_engine, speaker_engine

    logger.info("voice_service_starting")

    async def init_engines():
        loop = asyncio.get_event_loop()
        try:
            # STT
            stt = WhisperSTT(model_size="medium", device="auto")
            await loop.run_in_executor(None, stt.initialize)
            stt_engine = stt

            # TTS
            tts = PiperTTS(voice_id="ru_RU-denis-medium", speed=1.0)
            await loop.run_in_executor(None, tts.initialize)
            tts_engine = tts

            # Speaker recognition
            speaker = SpeakerRecognition(similarity_threshold=0.75)
            await loop.run_in_executor(None, speaker.initialize)
            speaker_engine = speaker

            logger.info("voice_service_ready")
        except Exception as e:
            logger.exception("voice_service_init_failed", error=str(e))
            raise

    await init_engines()

    yield

    stt_engine = None
    tts_engine = None
    speaker_engine = None
    logger.info("voice_service_stopped")


# --- App ---

app = FastAPI(
    title="KORGAN AI Voice Service",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Endpoints ---


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        stt_ready=stt_engine is not None,
        tts_ready=tts_engine is not None,
        speaker_ready=speaker_engine is not None,
    )


@app.post("/stt", response_model=STTResponse)
async def speech_to_text(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, etc.)"),
) -> STTResponse:
    """
    Transcribe audio to text using faster-whisper.
    """
    if stt_engine is None:
        raise HTTPException(503, "STT service not available")

    try:
        audio_bytes = await audio.read()
    except Exception as e:
        logger.warning("stt_read_failed", error=str(e))
        raise HTTPException(400, "Failed to read audio file")

    if not audio_bytes:
        raise HTTPException(400, "Empty audio file")

    try:
        text = await stt_engine.transcribe_async(audio_bytes)
        return STTResponse(text=text)
    except Exception as e:
        logger.exception("stt_failed", error=str(e))
        raise HTTPException(500, f"Transcription failed: {str(e)}")


@app.post("/tts")
async def text_to_speech(
    text: str = Form(..., min_length=1, max_length=10000),
) -> Response:
    """
    Synthesize text to audio using Piper TTS (Russian male voice).
    Returns WAV audio.
    """
    if tts_engine is None:
        raise HTTPException(503, "TTS service not available")

    try:
        audio_bytes = await tts_engine.synthesize_async(text.strip())
    except Exception as e:
        logger.exception("tts_failed", error=str(e))
        raise HTTPException(500, f"TTS failed: {str(e)}")

    if not audio_bytes:
        raise HTTPException(400, "Empty synthesis result")

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "attachment; filename=speech.wav",
        },
    )


@app.post("/verify-speaker", response_model=VerifySpeakerResponse)
async def verify_speaker(
    audio: UploadFile = File(..., description="Audio to verify against enrolled speaker"),
    speaker_id: str = Form("default", description="Enrolled speaker ID"),
) -> VerifySpeakerResponse:
    """
    Verify if the provided audio matches the enrolled speaker.
    Requires prior enrollment via enroll endpoint or loaded embedding.
    """
    if speaker_engine is None:
        raise HTTPException(503, "Speaker recognition service not available")

    try:
        audio_bytes = await audio.read()
    except Exception as e:
        logger.warning("verify_read_failed", error=str(e))
        raise HTTPException(400, "Failed to read audio file")

    if not audio_bytes:
        raise HTTPException(400, "Empty audio file")

    try:
        # Load enrollment if different speaker
        if speaker_engine._speaker_id != speaker_id:
            speaker_engine.load_enrollment(speaker_id)

        match, similarity = await speaker_engine.verify_async(audio_bytes)
        return VerifySpeakerResponse(match=match, similarity=round(similarity, 4))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("verify_speaker_failed", error=str(e))
        raise HTTPException(500, f"Verification failed: {str(e)}")


@app.post("/enroll-speaker")
async def enroll_speaker(
    audio_samples: List[UploadFile] = File(..., description="Audio samples for enrollment"),
    speaker_id: str = Form("default"),
) -> dict:
    """
    Enroll a new speaker from audio samples.
    """
    if speaker_engine is None:
        raise HTTPException(503, "Speaker recognition service not available")

    if len(audio_samples) < 1:
        raise HTTPException(400, "At least one audio sample required")

    try:
        samples = [await f.read() for f in audio_samples]
        await speaker_engine.enroll_async(samples, speaker_id)
        return {"status": "enrolled", "speaker_id": speaker_id}
    except Exception as e:
        logger.exception("enroll_failed", error=str(e))
        raise HTTPException(500, f"Enrollment failed: {str(e)}")


def run(host: str = "0.0.0.0", port: int = 8001) -> None:
    """Run the voice service."""
    import uvicorn
    uvicorn.run(
        "voice.service:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
