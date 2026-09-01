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
import threading
import time
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

        # Register on_prompt handler to inject mt_user_id into extra_pnginfo,
        # so preview persistence knows which user generated each image.
        def on_prompt(json_data):
            try:
                from .auth import verify_token
                # Extract user from the request context (set by middleware)
                user = getattr(server, "_mt_current_user", None)
                if user:
                    extra_data = json_data.setdefault("extra_data", {})
                    extra_pnginfo = extra_data.setdefault("extra_pnginfo", {})
                    extra_pnginfo["mt_user_id"] = str(user["id"])
                    # Ensure workflow id is present for preview grouping
                    if "workflow" not in extra_pnginfo:
                        extra_pnginfo["workflow"] = {}
            except Exception as e:
                logger.error(f"[ComfyUI-MT] on_prompt inject failed: {e}")
            return json_data

        try:
            server.add_on_prompt_handler(on_prompt)
            logger.info("[ComfyUI-MT] on_prompt handler registered (mt_user_id injection)")
        except Exception as e:
            logger.error(f"[ComfyUI-MT] add_on_prompt_handler failed: {e}")

        # Hook send_sync to capture "executed" events: each node that finishes
        # pushes {"node": node_id, "output": output_ui, "prompt_id": ...}.
        # When output has images, record the node_id -> filename mapping so
        # preview restore can match each PreviewImage node to its own image.
        try:
            original_send_sync = server.send_sync
            def patched_send_sync(event, data, sid=None):
                if event == "executed":
                    try:
                        _capture_executed_mapping(data)
                    except Exception:
                        pass
                return original_send_sync(event, data, sid)
            server.send_sync = patched_send_sync
            logger.info("[ComfyUI-MT] send_sync hooked (executed node->image mapping)")
        except Exception as e:
            logger.error(f"[ComfyUI-MT] send_sync hook failed: {e}")

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

    # If no valid user id (0 = unknown), still persist files but skip DB row
    # (FOREIGN KEY would fail). Files go under previews/0/ for cleanup-by-age.
    valid_user = user_id > 0

    # Extract workflow id from prompt — ComfyUI frontend stores it at
    # extra_pnginfo.workflow.id (from the workflow's saved id).
    workflow_id = "default"
    try:
        if extra_pnginfo and isinstance(extra_pnginfo, dict):
            wf = extra_pnginfo.get("workflow") or {}
            wf_id = wf.get("id") or wf.get("name") or ""
            if wf_id:
                workflow_id = str(wf_id)
            else:
                workflow_id = str(extra_pnginfo.get("workflow_name") or "default")
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

            # Destination: output/mt_previews/{user_id}/{workflow_id}/{filename}
            # Living in the output dir means the native /view?type=output
            # endpoint can serve it — the frontend restore path just writes
            # {filename, subfolder, type:'output'} into nodeOutputs and the
            # native image URL builder loads it. No custom image API needed.
            from folder_paths import get_output_directory
            dest_dir = os.path.join(
                get_output_directory(), "mt_previews", str(user_id), str(workflow_id)
            )
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, filename)

            # Copy (don't move — keep native temp behavior too)
            if not os.path.exists(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
                shutil.copy2(src, dest)

            # Record in DB (sync) — only when we have a real user id
            if valid_user:
                node_id = "preview"
                try:
                    db.execute(
                        """INSERT INTO preview_images (user_id, workflow_id, node_id, filename, file_path)
                           VALUES (?,?,?,?,?)
                           ON CONFLICT(user_id, workflow_id, node_id) DO UPDATE SET
                           filename=excluded.filename, file_path=excluded.file_path, created_at=datetime('now')""",
                        (user_id, workflow_id, node_id, filename, dest)
                    )
                    db.commit()
                except Exception as e:
                    logger.error(f"[ComfyUI-MT] Preview DB record failed: {e}")

            persisted.append({
                "filename": filename,
                "subfolder": str(workflow_id),
                "type": "temp",
                "mt_persisted": True,
                "mt_path": dest,
            })
        except Exception as e:
            logger.error(f"[ComfyUI-MT] Preview persist single failed: {e}")

    # NOTE: do NOT overwrite results["ui"]["images"]. The original images
    # reference the temp-dir files with subfolder="" and type="temp", which
    # the frontend's executed-event handler uses to render the LIVE preview
    # (buildImageUrls -> /view?type=temp). Replacing them with our persisted
    # entries (subfolder=<workflow_id>) broke live preview: the /view request
    # 404'd, so previews only appeared after F5 (when restore re-points to
    # output/mt_previews). Persistence is a side effect only — keep the
    # native results intact.

    return results


# In-memory queue of executed node->image mappings, flushed to DB in a
# background thread so we never block ComfyUI's execution thread/event loop.
_mapping_queue = []
_mapping_lock = threading.Lock()
_mapping_flusher = None


def _flush_mapping_queue() -> None:
    """Background thread: batch-write queued node->filename mappings to DB."""
    global _mapping_queue
    while True:
        try:
            time.sleep(2)
            with _mapping_lock:
                batch = _mapping_queue
                _mapping_queue = []
            if not batch:
                continue
            from .models import _get_db
            db = _get_db()
            try:
                for node_id, filename in batch:
                    db.execute(
                        "UPDATE preview_images SET node_id=? WHERE filename=? AND node_id='preview'",
                        (node_id, filename)
                    )
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        except Exception:
            time.sleep(5)


def _enqueue_mapping(node_id: str, filename: str) -> None:
    global _mapping_flusher
    with _mapping_lock:
        _mapping_queue.append((node_id, filename))
    if _mapping_flusher is None or not _mapping_flusher.is_alive():
        _mapping_flusher = threading.Thread(target=_flush_mapping_queue, daemon=True, name="mt-mapping-flusher")
        _mapping_flusher.start()


def _capture_executed_mapping(data: dict) -> None:
    """Queue node_id -> image filename mapping from an executed event (non-blocking)."""
    node_id = str(data.get("node", ""))
    output = data.get("output") or {}
    ui = output.get("ui") if isinstance(output, dict) else None
    images = (ui or output or {}).get("images") or []
    if not node_id or not images:
        return
    for img in images:
        if not isinstance(img, dict):
            continue
        filename = img.get("filename", "")
        if filename:
            _enqueue_mapping(node_id, filename)


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
