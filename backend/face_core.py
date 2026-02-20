import os
import cv2
import numpy as np
import logging

try:
    import onnxruntime
except ImportError:
    onnxruntime = None

from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)

# --- CONFIGURATION (from environment) ---
FACE_MODEL = os.environ.get('FACE_MODEL', 'buffalo_l')
MIN_FACE_SIZE = int(os.environ.get('MIN_FACE_SIZE', '40'))
MIN_DET_SCORE = float(os.environ.get('MIN_DET_SCORE', '0.5'))
DET_SIZE = int(os.environ.get('DET_SIZE', '640'))


def _get_providers():
    """Auto-detect GPU (CUDA) availability, fallback to CPU"""
    if onnxruntime and 'CUDAExecutionProvider' in onnxruntime.get_available_providers():
        logger.info("CUDA detected — using GPU acceleration")
        return ['CUDAExecutionProvider', 'CPUExecutionProvider']
    return ['CPUExecutionProvider']


class FaceModel:
    def __init__(self):
        self.model = None

    def load(self, verbose=True):
        """Initializes InsightFace model"""
        if self.model is None:
            providers = _get_providers()
            if verbose:
                logger.info(f"Loading InsightFace model '{FACE_MODEL}' with {providers[0]}...")
            self.model = FaceAnalysis(name=FACE_MODEL, providers=providers)
            self.model.prepare(ctx_id=0, det_size=(DET_SIZE, DET_SIZE))
            if verbose:
                logger.info(f"Model ready (512-dim vectors, det_size={DET_SIZE}x{DET_SIZE})")

    def _parse_input(self, image_input):
        """Convert bytes or numpy array to OpenCV BGR image"""
        if isinstance(image_input, bytes):
            nparr = np.frombuffer(image_input, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif isinstance(image_input, np.ndarray):
            return image_input
        return None

    def _filter_faces(self, faces):
        """Filter out low-quality detections (too small, low confidence)"""
        filtered = []
        for face in faces:
            w = face.bbox[2] - face.bbox[0]
            h = face.bbox[3] - face.bbox[1]
            if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
                continue
            if hasattr(face, 'det_score') and face.det_score < MIN_DET_SCORE:
                continue
            filtered.append(face)
        return filtered

    def get_vector(self, image_input):
        """
        Get the single best (largest) face embedding from an image.
        Used for employee registration.

        Input: bytes (from API) or numpy array (from camera)
        Output: (embedding_list, bbox_array) or (None, None)
        """
        if self.model is None:
            self.load()

        img = self._parse_input(image_input)
        if img is None:
            return None, None

        faces = self.model.get(img)
        if not faces:
            return None, None

        faces = self._filter_faces(faces)
        if not faces:
            return None, None

        # Sort by face area (largest first)
        faces = sorted(
            faces,
            key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]),
            reverse=True
        )
        target = faces[0]
        return target.embedding.tolist(), target.bbox.astype(int)

    def get_all_faces(self, image_input):
        """
        Detect and return ALL faces in the image.
        Used for multi-face detection in camera streams.

        Input: bytes or numpy array
        Output: list of dicts with 'embedding', 'bbox', 'det_score'
        """
        if self.model is None:
            self.load()

        img = self._parse_input(image_input)
        if img is None:
            return []

        faces = self.model.get(img)
        if not faces:
            return []

        faces = self._filter_faces(faces)

        # Sort by area (largest first)
        faces = sorted(
            faces,
            key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]),
            reverse=True
        )

        return [{
            'embedding': face.embedding,
            'bbox': face.bbox.astype(int).tolist(),
            'det_score': float(face.det_score) if hasattr(face, 'det_score') else 0.0,
        } for face in faces]


face_engine = FaceModel()
