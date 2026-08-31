"""Auth middleware + frontend injection for ComfyUI.

Strategy:
- ComfyUI's native frontend (axios) needs many /api/* endpoints to function
  (userdata, settings, object_info, system_stats, history, queue, etc.).
  Locking all of them breaks the UI.
- So we only REQUIRE auth for:
    * The main page `/` (serve login page when unauthenticated)
    * Admin-only endpoints (/api/mt/admin/*)
    * Model/template management endpoints (hidden from non-admin users)
    * Workflow execution endpoints (prompt/queue — prevent unauthenticated compute)
- Everything else passes through; authenticated users' requests carry their
  identity via mt_token cookie (set at login).
"""

import json
import logging
from aiohttp import web

from .auth import get_user_from_request

logger = logging.getLogger(__name__)

# Routes that never require auth
_PUBLIC_PATHS = {
    "/favicon.ico",
    "/api/mt/auth/login",
    "/api/mt/auth/register",
    "/api/mt/health",
    "/api/extensions",  # ComfyUI extension list (needed by frontend to load our JS)
    "/api/system_stats",
}

# Path prefixes that never require auth (static assets, ComfyUI core read-only)
_PUBLIC_PREFIXES = (
    "/assets/",
    "/extensions/",
    "/web/",
    "/fonts/",
    "/api/view",       # ComfyUI image view
    "/api/userdata",   # user's own data (workflows, settings) — needed by frontend
    "/api/user",       # user info (multi-user detection)
    "/api/settings",   # user settings
    "/api/object_info",# node definitions
    "/api/external",   # external resource info
    "/api/experiments",
    "/api/feature_flags",
    "/api/workflow_templates",
    "/api/models",     # model list — actually restricted below, keep public for now
)

# Execution/admin endpoints — require authentication
_AUTH_REQUIRED_PREFIXES = (
    "/api/prompt",      # submit workflow execution
    "/api/queue",       # queue management
    "/api/history",     # history
    "/api/interrupt",
    "/api/free",
    "/api/mt/admin/",   # admin endpoints
)

# Model/template management — hidden from non-admin users
_RESTRICTED_FOR_USER_PREFIXES = (
    "/api/models",
    "/api/model_",
    "/api/templates",
    "/api/userdata/models",
)


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _requires_auth(path: str) -> bool:
    for prefix in _AUTH_REQUIRED_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _is_restricted_for_user(path: str) -> bool:
    for prefix in _RESTRICTED_FOR_USER_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def setup_middleware(server):
    """Register auth middleware on the ComfyUI aiohttp app."""

    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        path = request.path

        # Public paths pass through (no auth needed)
        if _is_public_path(path) and not _requires_auth(path):
            return await handler(request)

        # Authenticate
        user = await get_user_from_request(request)

        # Main page: serve login page if not authenticated
        if path in ("/", "/index.html"):
            if not user:
                return await _serve_login_page(request)
            return await handler(request)

        # Execution endpoints require auth
        if _requires_auth(path):
            if not user:
                return web.json_response({"detail": "未登录"}, status=401)
            if not user.get("is_active", True):
                return web.json_response({"detail": "用户已被禁用"}, status=403)

        # Admin endpoints require admin
        if path.startswith("/api/mt/admin/") and not user:
            return web.json_response({"detail": "未登录"}, status=401)
        if path.startswith("/api/mt/admin/") and not user.get("is_admin", False):
            return web.json_response({"detail": "需要管理员权限"}, status=403)

        # Model/template endpoints restricted for non-admin
        if _is_restricted_for_user(path) and user is not None and not user.get("is_admin", False):
            return web.json_response({"detail": "需要管理员权限"}, status=403)

        # Attach user to request for downstream handlers
        if user:
            request["mt_user"] = user
        return await handler(request)

    # Register middleware (must be added before routes)
    server.app.middlewares.append(auth_middleware)
    logger.info("[ComfyUI-MT] Auth middleware registered")


async def _serve_login_page(request: web.Request) -> web.Response:
    """Serve the login page HTML."""
    from .frontend import get_login_page_html
    html = get_login_page_html()
    return web.Response(text=html, content_type="text/html")
