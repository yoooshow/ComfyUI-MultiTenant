"""ComfyUI Multi-Tenant Plugin — zero core modification entry point."""

import os
import logging

logger = logging.getLogger(__name__)

# ComfyUI custom_node protocol:
# - WEB_DIRECTORY: relative path to web extensions (auto-loaded by ComfyUI frontend)
# - NODE_CLASS_MAPPINGS / NODE_DISPLAY_NAME_MAPPINGS: we expose no nodes, just hooks

WEB_DIRECTORY = "./web"

# No custom nodes — this is a pure middleware/frontend plugin
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# ── Plugin lifecycle hooks (called by ComfyUI's server startup) ──

def setup_routes(server):
    """Called by ComfyUI PromptServer during route setup.

    We hook into the existing aiohttp app to:
    1. Add auth middleware (protect all routes except /auth/* and static)
    2. Add API routes (auth, workflows, previews, admin)
    3. Inject frontend overrides (hide features for non-admin)
    """
    from .middleware import setup_middleware
    from .routes import setup_api_routes

    logger.info("[ComfyUI-MT] Setting up multi-tenant plugin...")

    # 1. Initialize DB
    from .models import init_db_sync, get_user_sync, create_user_sync
    from .auth import hash_password
    from .config import get_db_path

    db_path = get_db_path(server)
    init_db_sync(db_path)

    # Ensure default admin exists
    admin = get_user_sync(db_path, username="admin")
    if not admin:
        create_user_sync(
            db_path,
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="Administrator",
            is_admin=True,
        )
        logger.info("[ComfyUI-MT] Default admin created: admin / admin123")

    # 2. Register middleware (auth guard)
    setup_middleware(server)

    # 3. Register API routes
    setup_api_routes(server)

    logger.info("[ComfyUI-MT] Multi-tenant plugin ready")
