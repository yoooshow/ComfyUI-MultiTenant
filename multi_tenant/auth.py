from __future__ import annotations
"""Authentication helpers — JWT tokens without external dependencies."""

import hashlib
import hmac
import json
import logging
import time
from aiohttp import web

from .config import get_secret_key
from .models import get_user

logger = logging.getLogger(__name__)

TOKEN_EXPIRY = 86400 * 7  # 7 days


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash)


def create_token(user_id: int, username: str) -> str:
    payload = {"user_id": user_id, "username": username, "exp": int(time.time()) + TOKEN_EXPIRY}
    payload_b64 = _b64encode(json.dumps(payload))
    signature = hmac.new(get_secret_key(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(get_secret_key(), payload_b64.encode(), hashlib.sha256).hexdigest()
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
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        token = request.query.get("token", "")
        if not token:
            return None
    else:
        token = auth_header[7:]
    payload = verify_token(token)
    if not payload:
        return None
    return await get_user(id=payload["user_id"])
