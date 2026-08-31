"""Plugin configuration — paths, constants, feature flags."""

import os


def get_db_path(server=None) -> str:
    """Resolve SQLite DB path. Prefer ComfyUI's user directory."""
    if server is not None:
        try:
            from folder_paths import get_user_directory
            user_dir = get_user_directory()
            db_dir = os.path.join(user_dir, "..", "mt_data")
            os.makedirs(db_dir, exist_ok=True)
            return os.path.join(db_dir, "mt.db")
        except Exception:
            pass
    # Fallback: plugin-local data directory
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    db_dir = os.path.join(plugin_dir, "..", "..", "..", "user", "mt_data")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "mt.db")


# ── Feature flags ──
# Billing is reserved but disabled. Set MT_BILLING=1 to enable stub.
BILLING_ENABLED = os.environ.get("MT_BILLING", "").strip().lower() in ("1", "true", "yes")

# Preview persistence: max age in seconds before cleanup (default 7 days)
PREVIEW_MAX_AGE = int(os.environ.get("MT_PREVIEW_MAX_AGE", str(86400 * 7)))

# Preview persistence: max total size per user in MB (default 500MB)
PREVIEW_MAX_SIZE_MB = int(os.environ.get("MT_PREVIEW_MAX_SIZE_MB", "500"))

# JWT token expiry: 7 days
TOKEN_EXPIRY = 86400 * 7
