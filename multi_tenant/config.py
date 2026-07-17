"""Shared configuration and state for the multi-tenant module."""

import os

_SECRET_KEY = None
_DB_PATH = None


def get_secret_key() -> bytes:
    global _SECRET_KEY
    if _SECRET_KEY is None:
        _SECRET_KEY = os.urandom(32)
    return _SECRET_KEY


def set_db_path(path: str):
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> str:
    return _DB_PATH


# Track pending bills: {prompt_id: {user_id, cost, prompt_name, start_time}}
pending_bills = {}
