from __future__ import annotations
import secrets
from pathlib import Path

from .config import AIVION_DIR

AUTH_TOKEN_PATH = AIVION_DIR / "auth-token"


def get_or_create_token() -> str:
    if AUTH_TOKEN_PATH.exists():
        token = AUTH_TOKEN_PATH.read_text().strip()
        if token:
            AUTH_TOKEN_PATH.chmod(0o600)
            return token
    AIVION_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    AUTH_TOKEN_PATH.write_text(token + "\n")
    AUTH_TOKEN_PATH.chmod(0o600)
    return token


def verify_token(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)
