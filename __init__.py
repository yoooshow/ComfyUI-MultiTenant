"""ComfyUI Multi-Tenant Plugin — V3 Extension Entry Point.

Zero core modification. Pure custom_node extension.
"""

import logging
import os
from typing import Optional

from comfy_api.latest import ComfyExtension, io

logger = logging.getLogger(__name__)


class MultiTenantExtension(ComfyExtension):
    """Multi-tenant extension for ComfyUI.

    Provides:
    - JWT authentication (admin/user roles)
    - Workflow management (Z&A shared / Custom per-user)
    - Preview image persistence
    - UI overrides (hide features for non-admin)
    """

    async def on_load(self) -> None:
        """Called when the extension is loaded."""
        logger.info("[ComfyUI-MT] Multi-tenant extension loading...")
        print("[ComfyUI-MT] on_load called")  # Debug print to stdout

        try:
            # Initialize database
            from .models import init_db_sync, get_user_sync, create_user_sync
            from .auth import hash_password
            from .config import get_db_path

            db_path = get_db_path()
            print(f"[ComfyUI-MT] DB path: {db_path}")
            init_db_sync(db_path)
            print("[ComfyUI-MT] DB initialized")

            # Ensure default admin exists (username: 15096756699, password: crd240108162)
            admin = get_user_sync(db_path, username="15096756699")
            if not admin:
                create_user_sync(
                    db_path,
                    username="15096756699",
                    password_hash=hash_password("crd240108162"),
                    display_name="Administrator",
                    is_admin=True,
                )
                logger.info("[ComfyUI-MT] Default admin created: 15096756699")
                print("[ComfyUI-MT] Admin created")
            else:
                print("[ComfyUI-MT] Admin already exists")

            # Register routes via PromptServer.instance
            import logging as _logging
            root_logger = _logging.getLogger()
            root_logger.info("[ComfyUI-MT] Registering routes...")
            result = await self._register_routes()
            root_logger.info(f"[ComfyUI-MT] Route registration result: {result}")

            # Setup preview persistence (monkey-patch PreviewImage)
            try:
                from .previews import setup_preview_persistence
                server = None
                import sys
                for module_name, module in sys.modules.items():
                    if module_name == 'server' or module_name.endswith('.server'):
                        if hasattr(module, 'PromptServer') and getattr(module, 'PromptServer').instance is not None:
                            server = getattr(module, 'PromptServer').instance
                            break
                if server:
                    setup_preview_persistence(server)
                    root_logger.info("[ComfyUI-MT] Preview persistence enabled")
            except Exception as e:
                root_logger.warning(f"[ComfyUI-MT] Preview persistence setup failed: {e}")

            # Write status to file for debugging
            try:
                from .config import get_db_path
                status_file = os.path.join(os.path.dirname(get_db_path()), "mt_status.txt")
                with open(status_file, "w") as f:
                    f.write(f"on_load completed at {__import__('datetime').datetime.now()}\n")
                    f.write(f"route_registration: {result}\n")
            except Exception:
                pass

            root_logger.info("[ComfyUI-MT] Multi-tenant extension loaded")
        except Exception as e:
            logger.error(f"[ComfyUI-MT] on_load failed: {e}")
            print(f"[ComfyUI-MT] on_load ERROR: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def _register_routes(self) -> bool:
        """Register routes on the PromptServer instance."""
        try:
            import sys
            from .middleware import setup_middleware
            from .routes import setup_api_routes

            # Find PromptServer instance from loaded modules
            server = None
            for module_name, module in sys.modules.items():
                if module_name == 'server' or module_name.endswith('.server'):
                    if hasattr(module, 'PromptServer'):
                        ps_class = getattr(module, 'PromptServer')
                        if hasattr(ps_class, 'instance') and ps_class.instance is not None:
                            server = ps_class.instance
                            break

            if server is None:
                logger.warning("[ComfyUI-MT] PromptServer instance not found, routes not registered")
                print("[ComfyUI-MT] PromptServer instance not found")
                return False

            logger.info("[ComfyUI-MT] Found PromptServer instance, registering routes...")
            print("[ComfyUI-MT] Found PromptServer instance")

            # Register middleware (auth guard)
            setup_middleware(server)

            # Register API routes
            setup_api_routes(server)

            logger.info("[ComfyUI-MT] Routes registered successfully")
            print("[ComfyUI-MT] Routes registered successfully")
            return True

        except Exception as e:
            logger.error(f"[ComfyUI-MT] Failed to register routes: {e}")
            print(f"[ComfyUI-MT] Route registration ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        """Return list of custom nodes. We expose no nodes — this is a middleware plugin."""
        return []


# V3 Extension entry point
def comfy_entrypoint() -> MultiTenantExtension:
    """ComfyUI V3 extension entry point."""
    return MultiTenantExtension()


# Web directory for frontend extensions (auto-loaded by ComfyUI)
WEB_DIRECTORY = "./web"
