"""Multi-tenant database models. Uses aiosqlite directly (ComfyUI dependency)."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_db = None
_db_path = None


async def init_db(db_path: str):
    """Initialize the SQLite database and create tables."""
    global _db, _db_path
    import aiosqlite

    _db_path = db_path
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = sqlite3.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            token_balance INTEGER DEFAULT 0 NOT NULL,
            is_admin INTEGER DEFAULT 0 NOT NULL,
            is_active INTEGER DEFAULT 1 NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL DEFAULT 0,
            transaction_type TEXT NOT NULL,
            reference_id TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS workflow_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            comfyui_workflow TEXT NOT NULL,
            base_cost INTEGER DEFAULT 10 NOT NULL,
            cost_per_step INTEGER DEFAULT 1 NOT NULL,
            cost_per_megapixel INTEGER DEFAULT 5 NOT NULL,
            is_active INTEGER DEFAULT 1 NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    await _db.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_user
        ON transactions(user_id)
    """)
    await _db.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_type
        ON transactions(transaction_type)
    """)

    await _db.commit()
    logger.info(f"Database initialized at {db_path}")


def get_db_conn():
    """Get the database connection (for use in sync contexts)."""
    return _db


async def get_user(username: Optional[str] = None, id: Optional[int] = None) -> Optional[dict]:
    """Look up a user by username or id."""
    if not _db:
        return None
    if username:
        cursor = await _db.execute("SELECT * FROM users WHERE username = ?", (username,))
    elif id is not None:
        cursor = await _db.execute("SELECT * FROM users WHERE id = ?", (id,))
    else:
        return None
    row = await cursor.fetchone()
    return dict(row) if row else None


async def create_user(username: str, password_hash: str, display_name: str = "",
                      token_balance: int = 0, is_admin: bool = False) -> Optional[dict]:
    """Create a new user."""
    if not _db:
        return None
    try:
        cursor = await _db.execute(
            "INSERT INTO users (username, password_hash, display_name, token_balance, is_admin) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, display_name or username, token_balance, 1 if is_admin else 0),
        )
        await _db.commit()
        return await get_user(id=cursor.lastrowid)
    except Exception as e:
        logger.warning(f"Failed to create user '{username}': {e}")
        return None


async def update_user_balance(user_id: int, delta: int) -> bool:
    """Update user balance by delta. Positive adds, negative subtracts."""
    if not _db:
        return False
    try:
        # Get current balance
        cursor = await _db.execute("SELECT token_balance FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            return False
        new_balance = row["token_balance"] + delta
        if new_balance < 0:
            return False  # Can't go below 0
        await _db.execute(
            "UPDATE users SET token_balance = ? WHERE id = ?",
            (new_balance, user_id),
        )
        await _db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update balance for user {user_id}: {e}")
        return False


async def create_transaction(user_id: int, amount: int, balance_after: int,
                              transaction_type: str, reference_id: str = "",
                              description: str = "") -> Optional[int]:
    """Create a transaction record."""
    if not _db:
        return None
    try:
        cursor = await _db.execute(
            "INSERT INTO transactions (user_id, amount, balance_after, transaction_type, reference_id, description) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, amount, balance_after, transaction_type, reference_id, description),
        )
        await _db.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Failed to create transaction: {e}")
        return None


async def get_all_users() -> list[dict]:
    """Get all users."""
    if not _db:
        return []
    cursor = await _db.execute("SELECT * FROM users ORDER BY id")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_transactions(user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    """Get transactions for a user."""
    if not _db:
        return []
    cursor = await _db.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_all_transactions(limit: int = 100, offset: int = 0) -> list[dict]:
    """Get all transactions (admin)."""
    if not _db:
        return []
    cursor = await _db.execute(
        "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_stats() -> dict:
    """Get system statistics."""
    if not _db:
        return {"total_users": 0, "total_transactions": 0, "total_tokens_consumed": 0}

    users = await _db.execute("SELECT COUNT(*) as c FROM users")
    total_users = (await users.fetchone())["c"]

    txns = await _db.execute("SELECT COUNT(*) as c FROM transactions")
    total_txns = (await txns.fetchone())["c"]

    consumed = await _db.execute(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as c FROM transactions WHERE amount < 0 AND transaction_type = 'deduction'"
    )
    total_consumed = (await consumed.fetchone())["c"]

    return {
        "total_users": total_users,
        "total_transactions": total_txns,
        "total_tokens_consumed": total_consumed,
    }


async def create_workflow_template(name: str, display_name: str, comfyui_workflow: dict,
                                    description: str = "", base_cost: int = 10,
                                    cost_per_step: int = 1, cost_per_megapixel: int = 5) -> Optional[dict]:
    """Create a workflow template."""
    if not _db:
        return None
    try:
        cursor = await _db.execute(
            "INSERT INTO workflow_templates (name, display_name, description, comfyui_workflow, base_cost, cost_per_step, cost_per_megapixel) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, display_name, description, json.dumps(comfyui_workflow), base_cost, cost_per_step, cost_per_megapixel),
        )
        await _db.commit()
        return {"id": cursor.lastrowid, "name": name, "display_name": display_name}
    except Exception as e:
        logger.warning(f"Failed to create workflow template: {e}")
        return None


async def get_workflow_templates(active_only: bool = True) -> list[dict]:
    """Get workflow templates."""
    if not _db:
        return []
    if active_only:
        cursor = await _db.execute("SELECT * FROM workflow_templates WHERE is_active = 1 ORDER BY display_name")
    else:
        cursor = await _db.execute("SELECT * FROM workflow_templates ORDER BY display_name")
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["comfyui_workflow"] = json.loads(d["comfyui_workflow"])
        except (json.JSONDecodeError, TypeError):
            d["comfyui_workflow"] = {}
        result.append(d)
    return result


async def delete_workflow_template(template_id: int) -> bool:
    """Delete a workflow template."""
    if not _db:
        return False
    try:
        await _db.execute("DELETE FROM workflow_templates WHERE id = ?", (template_id,))
        await _db.commit()
        return True
    except Exception:
        return False


def init_db_sync(db_path: str, loop=None) -> None:
    """Synchronous DB initialization — called from setup_routes_sync before server starts."""
    import os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            token_balance INTEGER DEFAULT 0 NOT NULL,
            is_admin INTEGER DEFAULT 0 NOT NULL,
            is_active INTEGER DEFAULT 1 NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL DEFAULT 0,
            transaction_type TEXT NOT NULL,
            reference_id TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            comfyui_workflow TEXT NOT NULL,
            base_cost INTEGER DEFAULT 10 NOT NULL,
            cost_per_step INTEGER DEFAULT 1 NOT NULL,
            cost_per_megapixel INTEGER DEFAULT 5 NOT NULL,
            is_active INTEGER DEFAULT 1 NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type)")
    conn.commit()
    conn.close()
    logging.getLogger(__name__).info(f"Database initialized (sync) at {db_path}")

    # Also initialize the async _db connection for use by async handlers
    if loop is not None:
        import asyncio
        async def _init_async():
            global _db
            import aiosqlite
            _db = await aiosqlite.connect(db_path)
            _db.row_factory = sqlite3.Row
        fut = asyncio.run_coroutine_threadsafe(_init_async(), loop)
        fut.result(timeout=30)
        logging.getLogger(__name__).debug("Async DB connection initialized")


def get_user_sync(db_path: str, username: str | None = None, user_id: int | None = None) -> dict | None:
    """Synchronous user lookup."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if username:
        cursor = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    elif user_id is not None:
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    else:
        conn.close()
        return None
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user_sync(db_path: str, username: str, password_hash: str, display_name: str = "",
                     token_balance: int = 0, is_admin: bool = False) -> dict | None:
    """Synchronous user creation."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, display_name, token_balance, is_admin) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, display_name or username, token_balance, 1 if is_admin else 0),
        )
        conn.commit()
        user_id = cursor.lastrowid
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        conn.close()
        raise
