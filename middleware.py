"""Auth middleware + frontend injection for ComfyUI."""

import json
import logging
from aiohttp import web

from .auth import get_user_from_request, verify_token

logger = logging.getLogger(__name__)

# Routes that don't require authentication
_PUBLIC_PATHS = {
    "/",
    "/index.html",
    "/favicon.ico",
    "/api/mt/auth/login",
    "/api/mt/auth/register",
    "/api/mt/health",
}

# Path prefixes that don't require authentication (static assets, ComfyUI core)
_PUBLIC_PREFIXES = (
    "/assets/",
    "/extensions/",
    "/web/",
    "/api/view",  # ComfyUI image view (protected separately by preview logic)
    "/ws",        # WebSocket (protected by token in query)
)


def _is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required)."""
    if path in _PUBLIC_PATHS:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _is_admin_path(path: str) -> bool:
    """Check if a path requires admin privileges."""
    return path.startswith("/api/mt/admin/")


def setup_middleware(server):
    """Register auth middleware on the ComfyUI aiohttp app."""

    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        path = request.path

        # Public paths pass through
        if _is_public_path(path):
            return await handler(request)

        # Check authentication
        user = await get_user_from_request(request)
        if not user:
            # For API requests, return 401 JSON
            if path.startswith("/api/"):
                return web.json_response({"detail": "未登录"}, status=401)
            # For page requests, serve login page
            return await _serve_login_page(request)

        if not user.get("is_active", True):
            return web.json_response({"detail": "用户已被禁用"}, status=403)

        # Admin path check
        if _is_admin_path(path) and not user.get("is_admin", False):
            return web.json_response({"detail": "需要管理员权限"}, status=403)

        # Attach user to request for downstream handlers
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


def inject_frontend_overrides(server):
    """Inject frontend overrides into ComfyUI's index.html response.

    This intercepts the main page and injects our CSS/JS to:
    - Hide Models/Templates/Console/Settings for non-admin users
    - Replace Settings with user menu
    - Add workflow management UI
    """
    # We do this by patching the existing index route
    # ComfyUI serves index.html from its web root
    pass  # Handled by web/ extension auto-loading
