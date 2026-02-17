"""Secure face embedding storage with AES-256-GCM encryption."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

logger = structlog.get_logger(__name__)

DEFAULT_EMBEDDINGS_DIR = Path.home() / ".korgan" / "vision" / "embeddings"
SALT_SIZE = 16
NONCE_SIZE = 12
KEY_SIZE = 32
ITERATIONS = 600_000


class EmbeddingStore:
    """
    File-based face embedding storage with AES-256-GCM encryption.
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        """
        Args:
            storage_dir: Directory for encrypted embedding files
        """
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_EMBEDDINGS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.storage_dir, 0o700)
        except OSError:
            pass

    def _derive_key(self, encryption_key: bytes) -> bytes:
        """Derive a 32-byte key from user-provided key using PBKDF2."""
        if len(encryption_key) < 16:
            raise ValueError("Encryption key must be at least 16 bytes")
        salt = b"korgan_vision_embedding_store"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(encryption_key[:64])  # Use up to 64 bytes of input

    def _encrypt(self, data: bytes, key: bytes) -> bytes:
        """Encrypt data with AES-256-GCM."""
        aesgcm = AESGCM(key)
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def _decrypt(self, encrypted_data: bytes, key: bytes) -> bytes:
        """Decrypt AES-256-GCM encrypted data."""
        if len(encrypted_data) < NONCE_SIZE:
            raise ValueError("Invalid encrypted data")
        nonce = encrypted_data[:NONCE_SIZE]
        ciphertext = encrypted_data[NONCE_SIZE:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def _get_user_path(self, user_id: str) -> Path:
        """Get storage path for user (sanitized)."""
        safe_id = "".join(c for c in user_id if c.isalnum() or c in "._-")
        if not safe_id:
            raise ValueError("Invalid user_id")
        return self.storage_dir / f"{safe_id}.enc"

    def save_embedding(
        self,
        user_id: str,
        embedding: np.ndarray,
        encryption_key: bytes,
    ) -> None:
        """
        Save face embedding with AES-256-GCM encryption.

        Args:
            user_id: User identifier
            embedding: 512-dim numpy array
            encryption_key: Bytes used to derive AES key (min 16 bytes)
        """
        emb = np.asarray(embedding, dtype=np.float32).flatten()
        if emb.size != 512:
            raise ValueError("Embedding must be 512-dimensional")

        key = self._derive_key(encryption_key)
        data = json.dumps({"embedding": emb.tolist(), "user_id": user_id}).encode("utf-8")
        encrypted = self._encrypt(data, key)

        path = self._get_user_path(user_id)
        path.write_bytes(encrypted)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

        logger.info("embedding_saved", user_id=user_id)

    def load_embedding(self, user_id: str, encryption_key: bytes) -> np.ndarray:
        """
        Load and decrypt face embedding.

        Args:
            user_id: User identifier
            encryption_key: Same key used during save

        Returns:
            512-dim numpy array

        Raises:
            FileNotFoundError: If no embedding for user_id
        """
        path = self._get_user_path(user_id)
        if not path.exists():
            raise FileNotFoundError(f"No enrollment found for user '{user_id}'")

        key = self._derive_key(encryption_key)
        encrypted = path.read_bytes()
        data = self._decrypt(encrypted, key).decode("utf-8")
        payload = json.loads(data)

        embedding = np.array(payload["embedding"], dtype=np.float32)
        if embedding.size != 512:
            raise ValueError("Stored embedding has invalid shape")
        return embedding

    def delete_embedding(self, user_id: str) -> None:
        """
        Delete stored embedding for user.

        Args:
            user_id: User identifier
        """
        path = self._get_user_path(user_id)
        if path.exists():
            path.unlink()
            logger.info("embedding_deleted", user_id=user_id)
        else:
            raise FileNotFoundError(f"No enrollment found for user '{user_id}'")

    def has_embedding(self, user_id: str) -> bool:
        """Check if user has an enrolled embedding."""
        return self._get_user_path(user_id).exists()
