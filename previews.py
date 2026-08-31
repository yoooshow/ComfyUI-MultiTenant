"""Preview image persistence — hook PreviewImage to save to persistent directory.

Strategy:
- Monkey-patch nodes.PreviewImage.save_images to ALSO write to a persistent
  directory (user/mt_data/previews/) so images survive ComfyUI restart.
- Record file locations in the DB (preview_images table) per user/workflow.
- Frontend restores previews via API when workflow reopens.
- Cleanup: when workflow tab is closed, frontend calls DELETE /api/mt/previews/{wf}
  which removes files + DB rows.

This keeps official ComfyUI untouched (runtime hook only).
"""

import logging
import os
import random
import shutil
import string
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Persistent preview root (under user dir). Set during setup.
_preview_root = None


def get_preview_root() -> str:
    """Return the persistent preview root directory."""
    global _preview_root
    if _preview_root is None:
        from .config import get_db_path
        db_path = get_db_path()
        _preview_root = os.path.join(os.path.dirname(db_path), "previews")
    os.makedirs(_preview_root, exist_ok=True)
    return _preview_root


def setup_preview_persistence(server) -> None:
    """Monkey-patch PreviewImage.save_images to persist to a stable dir."""
    try:
        import nodes
        from PIL import Image
        import numpy as np

        original_save_images = nodes.PreviewImage.save_images

        def persistent_save_images(self, images, filename_prefix="ComfyUI", prompt=None, extra_pnginfo=None):
            """Save to temp (native behavior) AND to persistent preview dir."""
            results = original_save_images(self, images, filename_prefix, prompt, extra_pnginfo)
            try:
                return _persist_results(self, results, images, prompt, extra_pnginfo)
            except Exception as e:
                logger.error(f"[ComfyUI-MT] Preview persistence failed: {e}")
                return results

        nodes.PreviewImage.save_images = persistent_save_images
        logger.info("[ComfyUI-MT] PreviewImage.save_images hooked for persistence")

        # Also hook the V3 PreviewImage if present
        try:
            from comfy_api.latest._ui import PreviewImage as V3PreviewImage
            if hasattr(V3PreviewImage, 'save_images'):
                v3_orig = V3PreviewImage.save_images
                def v3_persistent(self, images, filename_prefix="ComfyUI", prompt=None, extra_pnginfo=None):
                    results = v3_orig(self, images, filename_prefix, prompt, extra_pnginfo)
                    try:
                        return _persist_results(self, results, images, prompt, extra_pnginfo)
                    except Exception as e:
                        logger.error(f"[ComfyUI-MT] V3 Preview persistence failed: {e}")
                        return results
                V3PreviewImage.save_images = v3_persistent
                logger.info("[ComfyUI-MT] V3 PreviewImage.save_images hooked")
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[ComfyUI-MT] Failed to setup preview persistence: {e}")
        import traceback
        traceback.print_exc()


def _persist_results(self, results, images, prompt, extra_pnginfo) -> dict:
    """Copy preview images from temp to persistent dir and record in DB.

    Called from monkey-patched save_images (synchronous context).
    Uses synchronous DB helpers to avoid async/sync mismatch.
    """
    from .models import _get_db

    if not results or "ui" not in results or "images" not in results["ui"]:
        return results

    # Determine current user from prompt context (may be None for admin/local runs)
    user_id = 0
    try:
        if extra_pnginfo and isinstance(extra_pnginfo, dict):
            mt_user_id = extra_pnginfo.get("mt_user_id")
            if mt_user_id:
                user_id = int(mt_user_id)
    except Exception:
        pass

    # Extract workflow id from prompt
    workflow_id = "default"
    try:
        if extra_pnginfo and isinstance(extra_pnginfo, dict):
            workflow_id = str(extra_pnginfo.get("workflow_id") or extra_pnginfo.get("workflow_name") or "default")
    except Exception:
        pass

    # Copy each temp image to persistent dir
    preview_dir = get_preview_root()
    persisted = []
    db = _get_db()
    for img_ref in results["ui"]["images"]:
        try:
            filename = img_ref.get("filename", "")
            subfolder = img_ref.get("subfolder", "")

            if not filename:
                continue

            # Source path in temp dir
            from folder_paths import get_temp_directory
            src = os.path.join(get_temp_directory(), subfolder, filename)
            if not os.path.isfile(src):
                continue

            # Destination: previews/{user_id}/{workflow_id}/{filename}
            dest_dir = os.path.join(preview_dir, str(user_id), str(workflow_id))
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, filename)

            # Copy (don't move — keep native temp behavior too)
            if not os.path.exists(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
                shutil.copy2(src, dest)

            # Record in DB (sync)
            node_id = "preview"
            db.execute(
                """INSERT INTO preview_images (user_id, workflow_id, node_id, filename, file_path)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(user_id, workflow_id, node_id) DO UPDATE SET
                   filename=excluded.filename, file_path=excluded.file_path, created_at=datetime('now')""",
                (user_id, workflow_id, node_id, filename, dest)
            )
            db.commit()

            persisted.append({
                "filename": filename,
                "subfolder": str(workflow_id),
                "type": "temp",
                "mt_persisted": True,
                "mt_path": dest,
            })
        except Exception as e:
            logger.error(f"[ComfyUI-MT] Preview persist single failed: {e}")

    if persisted:
        results["ui"]["images"] = persisted

    return results


async def cleanup_preview_files(user_id: int, workflow_id: str) -> int:
    """Delete preview files + DB rows for a workflow (tab closed)."""
    from .models import get_preview_images, delete_preview_images
    previews = await get_preview_images(user_id, workflow_id)
    for p in previews:
        try:
            if os.path.isfile(p["file_path"]):
                os.remove(p["file_path"])
        except Exception:
            pass
    count = await delete_preview_images(user_id, workflow_id)
    return count
