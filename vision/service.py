"""FastAPI service for KORGAN AI Vision System (port 8002)."""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from vision.embeddings import EmbeddingStore
from vision.face_recognition import FaceBoundingBox, FaceRecognitionEngine
from vision.face_recognition import FACE_RECOGNITION_THRESHOLD

logger = structlog.get_logger(__name__)

# Global instances (initialized in lifespan)
face_engine: Optional[FaceRecognitionEngine] = None
embedding_store: Optional[EmbeddingStore] = None


# --- Pydantic Models ---


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="ok", description="Service status")
    face_engine_ready: bool = Field(description="Face recognition engine ready")


class FaceBBoxResponse(BaseModel):
    """Single face bounding box."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class DetectFaceResponse(BaseModel):
    """Face detection response."""

    faces: list[FaceBBoxResponse] = Field(description="Detected faces")


class VerifyFaceResponse(BaseModel):
    """Face verification response."""

    match: bool = Field(description="Whether the face matches enrolled")
    similarity: float = Field(ge=0.0, le=1.0, description="Similarity score")


class EnrollFaceResponse(BaseModel):
    """Face enrollment response."""

    status: str = Field(default="enrolled", description="Enrollment status")
    user_id: str = Field(description="Enrolled user ID")


# --- Lifespan ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize engines on startup, cleanup on shutdown."""
    global face_engine, embedding_store

    logger.info("vision_service_starting")

    async def init_engines():
        loop = asyncio.get_event_loop()
        try:
            face = FaceRecognitionEngine(
                similarity_threshold=FACE_RECOGNITION_THRESHOLD,
                use_gpu=True,
            )
            await loop.run_in_executor(None, face.initialize)
            face_engine = face

            embedding_store = EmbeddingStore()

            logger.info("vision_service_ready")
        except Exception as e:
            logger.exception("vision_service_init_failed", error=str(e))
            raise

    await init_engines()

    yield

    face_engine = None
    embedding_store = None
    logger.info("vision_service_stopped")


# --- App ---

app = FastAPI(
    title="KORGAN AI Vision Service",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Helpers ---


def _decode_encryption_key(key_b64: str) -> bytes:
    """Decode base64 encryption key."""
    try:
        return base64.b64decode(key_b64, validate=True)
    except Exception as e:
        raise HTTPException(400, f"Invalid encryption key encoding: {e}") from e


def _face_bbox_to_response(bbox: FaceBoundingBox) -> FaceBBoxResponse:
    """Convert FaceBoundingBox to response model (no embedding)."""
    return FaceBBoxResponse(
        x1=bbox.x1,
        y1=bbox.y1,
        x2=bbox.x2,
        y2=bbox.y2,
        confidence=bbox.confidence,
    )


# --- Endpoints ---


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        face_engine_ready=face_engine is not None,
    )


@app.post("/detect-face", response_model=DetectFaceResponse)
async def detect_face(
    image: UploadFile = File(..., description="Image file (JPEG, PNG, etc.)"),
) -> DetectFaceResponse:
    """
    Detect faces in image. Returns bounding boxes and confidence scores.
    """
    if face_engine is None:
        raise HTTPException(503, "Vision service not available")

    try:
        image_bytes = await image.read()
    except Exception as e:
        logger.warning("detect_read_failed", error=str(e))
        raise HTTPException(400, "Failed to read image file")

    if not image_bytes:
        raise HTTPException(400, "Empty image file")

    try:
        faces = await face_engine.detect_faces_async(image_bytes)
        return DetectFaceResponse(
            faces=[_face_bbox_to_response(f) for f in faces]
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("detect_face_failed", error=str(e))
        raise HTTPException(500, f"Face detection failed: {str(e)}")


@app.post("/verify-face", response_model=VerifyFaceResponse)
async def verify_face(
    image: UploadFile = File(..., description="Image containing face to verify"),
    user_id: str = Form(..., description="Enrolled user ID to verify against"),
    encryption_key: str = Form(..., description="Base64-encoded encryption key"),
) -> VerifyFaceResponse:
    """
    Verify if the face in the image matches the enrolled face for the given user.
    """
    if face_engine is None or embedding_store is None:
        raise HTTPException(503, "Vision service not available")

    try:
        image_bytes = await image.read()
    except Exception as e:
        logger.warning("verify_read_failed", error=str(e))
        raise HTTPException(400, "Failed to read image file")

    if not image_bytes:
        raise HTTPException(400, "Empty image file")

    try:
        key_bytes = _decode_encryption_key(encryption_key)
        enrolled = embedding_store.load_embedding(user_id, key_bytes)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        probe_embedding = await face_engine.get_embedding_async(image_bytes)
        match, similarity = face_engine.verify(probe_embedding, enrolled)
        return VerifyFaceResponse(match=match, similarity=round(similarity, 4))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("verify_face_failed", error=str(e))
        raise HTTPException(500, f"Face verification failed: {str(e)}")


@app.post("/enroll-face", response_model=EnrollFaceResponse)
async def enroll_face(
    image: UploadFile = File(..., description="Image containing a single face"),
    user_id: str = Form(..., description="User ID for enrollment"),
    encryption_key: str = Form(..., description="Base64-encoded encryption key"),
) -> EnrollFaceResponse:
    """
    Enroll a face from image. Stores encrypted 512-dim embedding.
    """
    if face_engine is None or embedding_store is None:
        raise HTTPException(503, "Vision service not available")

    try:
        image_bytes = await image.read()
    except Exception as e:
        logger.warning("enroll_read_failed", error=str(e))
        raise HTTPException(400, "Failed to read image file")

    if not image_bytes:
        raise HTTPException(400, "Empty image file")

    try:
        key_bytes = _decode_encryption_key(encryption_key)
    except HTTPException:
        raise

    try:
        embedding = await face_engine.get_embedding_async(image_bytes)
        embedding_store.save_embedding(user_id, embedding, key_bytes)
        return EnrollFaceResponse(status="enrolled", user_id=user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("enroll_face_failed", error=str(e))
        raise HTTPException(500, f"Face enrollment failed: {str(e)}")


def run(host: str = "0.0.0.0", port: int = 8002) -> None:
    """Run the vision service."""
    import uvicorn

    uvicorn.run(
        "vision.service:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
