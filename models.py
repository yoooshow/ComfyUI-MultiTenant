"""SQLite models — users, workflows, preview persistence."""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_db = None
_db_path = None


def init_db_sync(db_path: str):
    """Synchronous DB initialization (called during plugin setup)."""
    global _db, _db_path
    _db_path = db_path
    _db = sqlite3.connect(db_path, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    _db.execute("PRAGMA journal_mode=WAL")
    _db.execute("PRAGMA foreign_keys=ON")

    _db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0 NOT NULL,
            is_active INTEGER DEFAULT 1 NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            workflow_data TEXT NOT NULL,  -- JSON
            is_za_workflow INTEGER DEFAULT 0 NOT NULL,  -- 1 = Z&A shared, 0 = custom
            owner_id INTEGER,  -- NULL for Z&A workflows
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (owner_id) REFERENCES users(id),
            UNIQUE(name, owner_id)  -- Z&A workflows have owner_id=NULL
        );

        CREATE TABLE IF NOT EXISTS preview_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workflow_id TEXT NOT NULL,  -- ComfyUI's internal workflow/tab ID
            node_id TEXT NOT NULL,      -- PreviewImage node ID
            filename TEXT NOT NULL,     -- stored filename
            file_path TEXT NOT NULL,    -- absolute path
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, workflow_id, node_id)
        );

        CREATE INDEX IF NOT EXISTS idx_workflows_owner ON workflows(owner_id);
        CREATE INDEX IF NOT EXISTS idx_workflows_za ON workflows(is_za_workflow);
        CREATE INDEX IF NOT EXISTS idx_preview_user_wf ON preview_images(user_id, workflow_id);
    """)
    _db.commit()
    logger.info(f"[ComfyUI-MT] Database initialized at {db_path}")


def _get_db():
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db_sync first.")
    return _db


# ── User CRUD ──

async def get_user(id: int = None, username: str = None) -> Optional[dict]:
    db = _get_db()
    if id:
        row = db.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
    elif username:
        row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    else:
        return None
    return dict(row) if row else None


def get_user_sync(db_path: str, username: str) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user_sync(db_path: str, username: str, password_hash: str,
                     display_name: str = "", is_admin: bool = False) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, is_admin) VALUES (?,?,?,?)",
        (username, password_hash, display_name, 1 if is_admin else 0)
    )
    conn.commit()
    user_id = cursor.lastrowid
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


async def create_user(username: str, password_hash: str, display_name: str = "",
                      is_admin: bool = False) -> Optional[dict]:
    db = _get_db()
    try:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, display_name, is_admin) VALUES (?,?,?,?)",
            (username, password_hash, display_name, 1 if is_admin else 0)
        )
        db.commit()
        return await get_user(id=cursor.lastrowid)
    except sqlite3.IntegrityError:
        return None


async def get_all_users() -> list[dict]:
    db = _get_db()
    rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


async def update_user(user_id: int, **kwargs) -> bool:
    db = _get_db()
    allowed = {"display_name", "is_active", "is_admin", "password_hash"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [user_id]
    db.execute(f"UPDATE users SET {set_clause} WHERE id=?", values)
    db.commit()
    return True


# ── Workflow CRUD ──

async def create_workflow(name: str, workflow_data: dict, owner_id: int = None,
                          display_name: str = "", description: str = "",
                          is_za: bool = False) -> Optional[dict]:
    db = _get_db()
    try:
        cursor = db.execute(
            """INSERT INTO workflows (name, display_name, description, workflow_data, is_za_workflow, owner_id)
               VALUES (?,?,?,?,?,?)""",
            (name, display_name or name, description, json.dumps(workflow_data),
             1 if is_za else 0, owner_id)
        )
        db.commit()
        return await get_workflow(id=cursor.lastrowid)
    except sqlite3.IntegrityError:
        return None


async def get_workflow(id: int = None, name: str = None, owner_id: int = None) -> Optional[dict]:
    db = _get_db()
    if id:
        row = db.execute("SELECT * FROM workflows WHERE id=?", (id,)).fetchone()
    elif name and owner_id is not None:
        row = db.execute("SELECT * FROM workflows WHERE name=? AND owner_id=?", (name, owner_id)).fetchone()
    elif name:
        # Z&A workflow (owner_id IS NULL)
        row = db.execute("SELECT * FROM workflows WHERE name=? AND owner_id IS NULL", (name,)).fetchone()
    else:
        return None
    return dict(row) if row else None


async def get_workflows_for_user(user_id: int, include_za: bool = True) -> list[dict]:
    """Get all workflows visible to a user: their custom + optionally Z&A shared."""
    db = _get_db()
    if include_za:
        rows = db.execute(
            "SELECT * FROM workflows WHERE owner_id=? OR is_za_workflow=1 ORDER BY is_za_workflow DESC, name",
            (user_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM workflows WHERE owner_id=? ORDER BY name",
            (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


async def get_all_workflows() -> list[dict]:
    """Admin: get all workflows."""
    db = _get_db()
    rows = db.execute("SELECT * FROM workflows ORDER BY is_za_workflow DESC, name").fetchall()
    return [dict(r) for r in rows]


async def update_workflow(workflow_id: int, **kwargs) -> bool:
    db = _get_db()
    allowed = {"display_name", "description", "workflow_data", "is_za_workflow"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if "workflow_data" in updates:
        updates["workflow_data"] = json.dumps(updates["workflow_data"])
    if not updates:
        return False
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [workflow_id]
    db.execute(f"UPDATE workflows SET {set_clause} WHERE id=?", values)
    db.commit()
    return True


async def delete_workflow(workflow_id: int) -> bool:
    db = _get_db()
    cursor = db.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
    db.commit()
    return cursor.rowcount > 0


# ── Preview Image Persistence ──

async def save_preview_image(user_id: int, workflow_id: str, node_id: str,
                             filename: str, file_path: str) -> bool:
    """Save or update a preview image reference."""
    db = _get_db()
    db.execute(
        """INSERT INTO preview_images (user_id, workflow_id, node_id, filename, file_path)
           VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, workflow_id, node_id) DO UPDATE SET
           filename=excluded.filename, file_path=excluded.file_path, created_at=datetime('now')""",
        (user_id, workflow_id, node_id, filename, file_path)
    )
    db.commit()
    return True


async def get_preview_images(user_id: int, workflow_id: str) -> list[dict]:
    """Get all preview images for a user's workflow."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM preview_images WHERE user_id=? AND workflow_id=?",
        (user_id, workflow_id)
    ).fetchall()
    return [dict(r) for r in rows]


async def delete_preview_images(user_id: int, workflow_id: str) -> int:
    """Delete all preview images for a workflow (called when tab closed). Returns count."""
    db = _get_db()
    cursor = db.execute(
        "DELETE FROM preview_images WHERE user_id=? AND workflow_id=?",
        (user_id, workflow_id)
    )
    db.commit()
    return cursor.rowcount


async def cleanup_old_previews(max_age_seconds: int) -> int:
    """Remove preview image records older than max_age. Returns count."""
    db = _get_db()
    cursor = db.execute(
        "DELETE FROM preview_images WHERE created_at < datetime('now', ?)",
        (f"-{max_age_seconds} seconds",)
    )
    db.commit()
    return cursor.rowcount
