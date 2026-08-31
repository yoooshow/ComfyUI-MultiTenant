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
    # NOTE: /api/models is intentionally NOT public — it is restricted to
    # admins via _RESTRICTED_FOR_USER_PREFIXES below. Keeping it here made
    # the public check short-circuit before the restricted check ran.
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

# Model/template/manager/settings — hidden from non-admin users
# (both UI entry and API access are blocked for non-admin)
_RESTRICTED_FOR_USER_PREFIXES = (
    "/api/models",           # model library list/manage
    "/api/model_",           # model download/upload/etc
    "/api/templates",        # workflow templates
    "/api/userdata/models",  # user model data
    "/manager/",             # ComfyUI-Manager (install/update nodes & models)
    "/api/manager",          # manager API alternate prefix
    "/api/settings",         # settings write (GET is public-ish for UI)
    "/api/system_stats",     # system stats (resource info)
    "/api/userdata/audit",   # audit log
)
# Settings GET must remain readable by the frontend for non-admin UI;
# only block writes (PUT/POST). Handled in middleware below.


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

        # Authenticate first (cheap — cookie/header lookup)
        user = await get_user_from_request(request)

        # Restricted-for-user endpoints must be checked BEFORE the public
        # pass-through, otherwise the public prefix list short-circuits and
        # the restriction never runs.
        if _is_restricted_for_user(path):
            if user is None:
                return web.json_response({"detail": "未登录"}, status=401)
            if not user.get("is_admin", False):
                # Settings GET stays readable so the frontend can render;
                # block only settings writes (PUT/POST).
                if path.startswith("/api/settings") and request.method == "GET":
                    pass
                else:
                    return web.json_response({"detail": "需要管理员权限"}, status=403)

        # Public paths pass through (no auth needed)
        if _is_public_path(path) and not _requires_auth(path):
            return await handler(request)

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
            # Also stash on server for on_prompt handlers (which lack request context)
            try:
                server._mt_current_user = user
            except Exception:
                pass
        return await handler(request)

    # Register middleware (must be added before routes)
    server.app.middlewares.append(auth_middleware)
    logger.info("[ComfyUI-MT] Auth middleware registered")


async def _serve_login_page(request: web.Request) -> web.Response:
    """Serve the login page HTML."""
    from .frontend import get_login_page_html
    html = get_login_page_html()
    return web.Response(text=html, content_type="text/html")
