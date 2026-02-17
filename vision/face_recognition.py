"""Face recognition engine using InsightFace (RetinaFace + ArcFace)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

FACE_RECOGNITION_THRESHOLD = 0.6


@dataclass
class FaceBoundingBox:
    """Face detection result with bounding box and confidence."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    embedding: Optional[np.ndarray] = None


class FaceRecognitionEngine:
    """
    Face recognition using InsightFace.
    RetinaFace for detection, ArcFace for embeddings.
    GPU support via ONNX Runtime.
    """

    def __init__(
        self,
        similarity_threshold: float = FACE_RECOGNITION_THRESHOLD,
        use_gpu: bool = True,
        det_size: Tuple[int, int] = (640, 640),
    ) -> None:
        """
        Args:
            similarity_threshold: Minimum similarity for face match (0.0-1.0)
            use_gpu: Use CUDA via ONNX Runtime when available
            det_size: Detection input size (width, height)
        """
        self.similarity_threshold = similarity_threshold
        self.use_gpu = use_gpu
        self.det_size = det_size
        self._app: Optional[object] = None

    def initialize(self) -> None:
        """Load InsightFace models. Call before detect/get_embedding/compare."""
        if self._app is not None:
            logger.warning("face_recognition_already_initialized")
            return

        try:
            from insightface.app import FaceAnalysis

            providers = ["CPUExecutionProvider"]
            if self.use_gpu:
                try:
                    import onnxruntime as ort

                    if "CUDAExecutionProvider" in ort.get_available_providers():
                        providers.insert(0, "CUDAExecutionProvider")
                        logger.info("face_recognition_using_gpu")
                except ImportError:
                    pass

            self._app = FaceAnalysis(
                name="buffalo_l",
                root=None,
                providers=providers,
            )
            self._app.prepare(ctx_id=0, det_size=self.det_size)
            logger.info(
                "face_recognition_initialized",
                providers=providers,
                threshold=self.similarity_threshold,
            )
        except Exception as e:
            logger.exception("face_recognition_init_failed", error=str(e))
            raise

    def _ensure_initialized(self) -> None:
        """Raise if engine not initialized."""
        if self._app is None:
            raise RuntimeError(
                "FaceRecognitionEngine not initialized. Call initialize() first."
            )

    def _bytes_to_image(self, image_bytes: bytes) -> np.ndarray:
        """Decode image bytes to BGR numpy array."""
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Invalid or unsupported image format")
        return img

    def detect_faces(self, image_bytes: bytes) -> List[FaceBoundingBox]:
        """
        Detect faces in image.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.)

        Returns:
            List of face bounding boxes with confidence scores
        """
        self._ensure_initialized()
        img = self._bytes_to_image(image_bytes)
        faces = self._app.get(img)

        results: List[FaceBoundingBox] = []
        for face in faces:
            bbox = face.bbox  # [x1, y1, x2, y2]
            det_score = float(getattr(face, "det_score", 1.0))
            results.append(
                FaceBoundingBox(
                    x1=float(bbox[0]),
                    y1=float(bbox[1]),
                    x2=float(bbox[2]),
                    y2=float(bbox[3]),
                    confidence=det_score,
                    embedding=face.normed_embedding.copy() if hasattr(face, "normed_embedding") else None,
                )
            )
        return results

    def get_embedding(self, image_bytes: bytes) -> np.ndarray:
        """
        Extract 512-dim face embedding from image.
        Uses the largest/lone detected face.

        Args:
            image_bytes: Raw image bytes containing a single face

        Returns:
            512-dimensional numpy array (normalized embedding)

        Raises:
            ValueError: If no face or multiple faces detected
        """
        self._ensure_initialized()
        faces = self.detect_faces(image_bytes)

        if not faces:
            raise ValueError("No face detected in image")
        if len(faces) > 1:
            raise ValueError(f"Multiple faces ({len(faces)}) detected; single face required")

        face = faces[0]
        if face.embedding is not None:
            return face.embedding

        # Fallback: get embedding from FaceAnalysis (faces already have normed_embedding)
        img = self._bytes_to_image(image_bytes)
        detected = self._app.get(img)
        if not detected:
            raise ValueError("No face detected in image")
        return detected[0].normed_embedding

    def compare(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute similarity score between two embeddings.
        Uses cosine similarity (dot product for normalized embeddings).

        Args:
            embedding1: First 512-dim embedding
            embedding2: Second 512-dim embedding

        Returns:
            Similarity score in [0, 1] (1.0 = identical)
        """
        emb1 = np.asarray(embedding1, dtype=np.float32).flatten()
        emb2 = np.asarray(embedding2, dtype=np.float32).flatten()
        if emb1.shape != emb2.shape or emb1.size != 512:
            raise ValueError("Embeddings must be 512-dimensional")

        similarity = float(np.dot(emb1, emb2))
        # ArcFace normed_embedding is L2-normalized, so dot = cosine sim
        # Clamp to [0, 1] for typical similarity range
        return max(0.0, min(1.0, similarity))

    def verify(
        self, probe_embedding: np.ndarray, enrolled_embedding: np.ndarray
    ) -> Tuple[bool, float]:
        """
        Verify if probe matches enrolled face.

        Returns:
            Tuple of (match: bool, similarity: float)
        """
        similarity = self.compare(probe_embedding, enrolled_embedding)
        match = similarity >= self.similarity_threshold
        return match, similarity

    async def detect_faces_async(self, image_bytes: bytes) -> List[FaceBoundingBox]:
        """Async wrapper for detect_faces."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.detect_faces, image_bytes)

    async def get_embedding_async(self, image_bytes: bytes) -> np.ndarray:
        """Async wrapper for get_embedding."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_embedding, image_bytes)
