"""User isolation + Z&A workflow file sync.

ComfyUI's native userdata (workflows/settings) is keyed by user id from
`UserManager.get_request_user_id()`. By default (no --multi-user) every
request resolves to "default", so all users share one directory.

We patch get_request_user_id to resolve our JWT cookie to `mt_{user_id}`,
giving each user their own userdata directory (custom workflows isolated).

Z&A (shared) workflows are written as real .json files into the user's
workflows directory, so they appear in ComfyUI's native workflow browser.
On create/delete we sync them to every existing user's directory.
"""

import json
import logging
import os
import shutil

logger = logging.getLogger(__name__)


def _user_id_for_request(request) -> str | None:
    """Resolve MT user id (mt_{id}) from request cookie/token, or None."""
    try:
        from .auth import verify_token
        token = request.cookies.get("mt_token", "")
        if not token:
            token = request.query.get("token", "")
        payload = verify_token(token) if token else None
        if payload:
            return f"mt_{payload['user_id']}"
    except Exception:
        pass
    return None


def setup_user_isolation(server) -> None:
    """Patch UserManager.get_request_user_id to isolate per MT user."""
    try:
        from app.user_manager import UserManager

        original_get_request_user_id = UserManager.get_request_user_id

        def patched_get_request_user_id(self, request):
            mt_uid = _user_id_for_request(request)
            if mt_uid:
                # Ensure the user is registered in self.users so directory access works
                if mt_uid not in self.users:
                    try:
                        from .auth import verify_token
                        token = request.cookies.get("mt_token", "")
                        if not token:
                            token = request.query.get("token", "")
                        payload = verify_token(token) if token else None
                        self.users[mt_uid] = (payload or {}).get("username", mt_uid)
                    except Exception:
                        self.users[mt_uid] = mt_uid
                return mt_uid
            return original_get_request_user_id(self, request)

        UserManager.get_request_user_id = patched_get_request_user_id
        logger.info("[ComfyUI-MT] UserManager.get_request_user_id patched for per-user isolation")
    except Exception as e:
        logger.error(f"[ComfyUI-MT] Failed to patch user isolation: {e}")


# Sub-directory name for shared Z&A workflows inside each user's workflows dir.
# ComfyUI's native workflow browser renders subdirectories as folders, so
# shared workflows are visually separated from custom ones.
ZA_SUBDIR = "Z&A"


def _workflows_dir_for_user(user_id: str) -> str:
    """Return user workflows directory path."""
    from folder_paths import get_public_user_directory, get_user_directory
    user_root = get_public_user_directory(user_id)
    if user_root is None:
        user_root = os.path.join(get_user_directory(), user_id)
    wf_dir = os.path.join(user_root, "workflows")
    os.makedirs(wf_dir, exist_ok=True)
    return wf_dir


def _za_workflows_dir_for_user(user_id: str) -> str:
    """Return the Z&A shared subdirectory inside a user's workflows dir."""
    wf_dir = _workflows_dir_for_user(user_id)
    za_dir = os.path.join(wf_dir, ZA_SUBDIR)
    os.makedirs(za_dir, exist_ok=True)
    return za_dir


def _all_mt_user_ids() -> list[str]:
    """Return all known MT user dir ids (mt_{id})."""
    from .models import _get_db
    try:
        db = _get_db()
        rows = db.execute("SELECT id FROM users").fetchall()
        return [f"mt_{r['id']}" for r in rows]
    except Exception:
        return []


def sync_za_workflow_to_users(workflow_data: dict, display_name: str) -> None:
    """Write a Z&A workflow JSON into every user's Z&A subdirectory.

    Called after a Z&A workflow is created. The workflow file uses the
    display_name as filename (matching ComfyUI workflow browser conventions).
    Files land in workflows/Z&A/ so the native browser shows a shared folder
    separate from custom workflows.
    """
    try:
        # Filename sanitization: keep chars safe for filesystem
        safe_name = "".join(c for c in display_name if c not in '/\\:*?"<>|').strip() or "workflow"
        content = json.dumps(workflow_data, ensure_ascii=False, indent=2)

        for user_id in _all_mt_user_ids():
            za_dir = _za_workflows_dir_for_user(user_id)
            dest = os.path.join(za_dir, f"{safe_name}.json")
            with open(dest, "w", encoding="utf-8") as f:
                f.write(content)
        logger.info(f"[ComfyUI-MT] Z&A workflow '{display_name}' synced to {len(_all_mt_user_ids())} users (Z&A subdir)")
    except Exception as e:
        logger.error(f"[ComfyUI-MT] Z&A sync failed: {e}")


def remove_za_workflow_from_users(display_name: str) -> None:
    """Remove a Z&A workflow JSON from every user's Z&A subdirectory."""
    try:
        safe_name = "".join(c for c in display_name if c not in '/\\:*?"<>|').strip() or "workflow"
        for user_id in _all_mt_user_ids():
            za_dir = _za_workflows_dir_for_user(user_id)
            dest = os.path.join(za_dir, f"{safe_name}.json")
            if os.path.isfile(dest):
                os.remove(dest)
        logger.info(f"[ComfyUI-MT] Z&A workflow '{display_name}' removed from users (Z&A subdir)")
    except Exception as e:
        logger.error(f"[ComfyUI-MT] Z&A remove failed: {e}")


def resync_all_za_workflows() -> None:
    """Sync all Z&A workflows from DB to all users (run at startup)."""
    try:
        from .models import _get_db
        db = _get_db()
        rows = db.execute("SELECT display_name, workflow_data FROM workflows WHERE is_za_workflow=1").fetchall()
        for row in rows:
            try:
                wf_data = json.loads(row["workflow_data"])
                sync_za_workflow_to_users(wf_data, row["display_name"])
            except Exception as e:
                logger.error(f"[ComfyUI-MT] resync single Z&A failed: {e}")
    except Exception as e:
        logger.error(f"[ComfyUI-MT] resync Z&A failed: {e}")
