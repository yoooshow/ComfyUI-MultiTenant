"""Authentication — JWT tokens without external dependencies."""

import hashlib
import hmac
import json
import logging
import time
from aiohttp import web

logger = logging.getLogger(__name__)

TOKEN_EXPIRY = 86400 * 7  # 7 days


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash)


def _get_secret_key() -> bytes:
    """Get or create the JWT secret key. Stored in a file for persistence."""
    from .config import get_db_path
    import os
    key_file = os.path.join(os.path.dirname(get_db_path()), "jwt_secret.key")
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read()
    key = os.urandom(32)
    with open(key_file, "wb") as f:
        f.write(key)
    return key


def create_token(user_id: int, username: str) -> str:
    payload = {"user_id": user_id, "username": username, "exp": int(time.time()) + TOKEN_EXPIRY}
    payload_b64 = _b64encode(json.dumps(payload))
    signature = hmac.new(_get_secret_key(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(_get_secret_key(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(_b64decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _b64encode(data: str) -> str:
    import base64
    return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")


def _b64decode(data: str) -> str:
    import base64
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data).decode()


async def get_user_from_request(request: web.Request) -> dict | None:
    """Extract authenticated user from request. Returns None if not authenticated."""
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.query.get("token", "")
    if not token:
        return None
    payload = verify_token(token)
    if not payload:
        return None
    from .models import get_user
    return await get_user(id=payload["user_id"])
