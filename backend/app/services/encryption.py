"""Fernet symmetric encryption for OAuth token storage."""

import base64
import os

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        # Generate a key for local dev (not production safe — set ENCRYPTION_KEY env var)
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return a URL-safe base64 token."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def generate_encryption_key() -> str:
    """Helper to generate a new Fernet key (run once and store in env)."""
    return Fernet.generate_key().decode()
