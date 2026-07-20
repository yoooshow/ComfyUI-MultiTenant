"""ComfyUI Multi-Tenant — built-in billing and user management."""

import asyncio
import logging
import os
import time as time_module

from aiohttp import web

from .models import init_db, get_user, create_user, create_transaction, update_user_balance
from .routes import setup_routes
from .frontend import inject_frontend
from .config import set_db_path, pending_bills

logger = logging.getLogger(__name__)


def setup_routes_sync(server):
    """Synchronous route/middleware setup — called directly from add_routes().

    Initializes DB, creates admin user, registers routes.
    All synchronous — runs before any requests arrive.
    """
    # 1. Initialize database synchronously
    from folder_paths import get_user_directory
    user_dir = get_user_directory()
    db_dir = os.path.join(user_dir, "..", "multi_tenant_data")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "billing.db")
    set_db_path(db_path)

    from .models import init_db_sync, get_user_sync, create_user_sync
    init_db_sync(db_path)

    # Create default admin user if not exists
    from .auth import hash_password
    admin = get_user_sync(db_path, username="admin")
    if not admin:
        admin = create_user_sync(
            db_path,
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="Administrator",
            token_balance=999999,
            is_admin=True,
        )
        logger.info("Default admin created: admin / admin123 (balance: 999999)")
    # Reset admin password + balance (in case old DB has different hash)
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET token_balance = 999999, password_hash = ? WHERE username = 'admin'", (hash_password("admin123"),))
    conn.commit()
    conn.close()

    # 2. Register API routes
    from aiohttp import web as aiohttp_web
    our_routes = aiohttp_web.RouteTableDef()

    original_routes = server.routes
    server.routes = our_routes
    try:
        setup_routes(server)
    finally:
        server.routes = original_routes

    server.app.add_routes(our_routes)
    logger.info("Multi-tenant routes registered (sync)")



async def setup(server):
    """Initialize multi-tenant system. Called from server.py in a background task."""
    logger.info("Initializing Multi-Tenant billing system (async)...")

    from folder_paths import get_user_directory
    user_dir = get_user_directory()
    db_dir = os.path.join(user_dir, "..", "multi_tenant_data")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "billing.db")
    set_db_path(db_path)
    await init_db(db_path)

    # Create default admin user if not exists
    from .auth import hash_password
    admin = await get_user(username="admin")
    if not admin:
        admin = await create_user(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="Administrator",
            token_balance=999999,
            is_admin=True,
        )
        logger.info("Default admin created: admin / admin123 (balance: 999999)")
    else:
        await update_user_balance(admin["id"], 999999)

    # Wrap the prompt handler to add billing check
    _wrap_prompt_handler(server)

    # Start background task to poll for completed prompts
    poller_task = asyncio.create_task(_billing_poller(server))
    server._multi_tenant_poller = poller_task

    logger.info("Multi-Tenant billing system ready.")


def _wrap_prompt_handler(server):
    """Wrap the post_prompt handler to check billing before queuing."""
    for route in server.routes:
        if hasattr(route, "method") and route.method == "POST" and hasattr(route, "path") and route.path == "/prompt":
            original_handler = route.handler
            break
    else:
        logger.warning("Could not find /prompt route to wrap")
        return

    async def wrapped_post_prompt(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        from .auth import get_user_from_request
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"error": "请先登录"}, status=401)

        from .billing import calculate_cost
        cost = calculate_cost(body, user=user)

        if user["token_balance"] < cost:
            return web.json_response({
                "error": f"通证不足 (需要 {cost}, 当前 {user['token_balance']})"
            }, status=402)

        user_id = user["id"]
        await update_user_balance(user_id, -cost)
        prompt_name = body.get("prompt", {}).get("_meta", {}).get("title", "unknown")
        await create_transaction(
            user_id=user_id, amount=-cost,
            balance_after=user["token_balance"] - cost,
            transaction_type="deduction_hold",
            reference_id="hold", description=f"执行: {prompt_name}",
        )

        response = await original_handler(request)

        if response.status == 200:
            try:
                result = await response.json()
                prompt_id = result.get("prompt_id", "")
                if prompt_id:
                    pending_bills[prompt_id] = {
                        "user_id": user_id, "cost": cost,
                        "prompt_name": prompt_name,
                        "start_time": time_module.time(),
                    }
            except Exception:
                pass

        return response

    try:
        route.handler = wrapped_post_prompt
        logger.info("Prompt handler wrapped with billing check")
    except Exception:
        logger.warning("Could not wrap prompt handler (route frozen). Billing via lock script.")


async def _billing_poller(server, interval: float = 3.0, timeout: float = 600.0):
    """Poll for completed prompts and finalize billing."""
    from .config import pending_bills as _pb

    logger.info("Billing poller started")
    while True:
        await asyncio.sleep(interval)
        now = time_module.time()
        completed_ids = []

        for prompt_id, info in list(_pb.items()):
            elapsed = now - info["start_time"]
            if elapsed > timeout:
                user_id = info["user_id"]
                cost = info["cost"]
                await update_user_balance(user_id, cost)
                await create_transaction(
                    user_id=user_id, amount=cost, balance_after=0,
                    transaction_type="refund", reference_id=prompt_id,
                    description=f"退款: 执行超时 ({info['prompt_name']})",
                )
                logger.info(f"Refund {cost} for prompt {prompt_id} (timeout)")
                completed_ids.append(prompt_id)
                continue

            try:
                history = server.prompt_queue.get_history(prompt_id)
            except Exception:
                history = None

            if history is not None:
                status = history.get(prompt_id, {})
                outputs = status.get("outputs", {})
                status_info = status.get("status", {})
                success = status_info.get("completed") is True or status_info.get("status_str") == "success"

                user_id = info["user_id"]
                cost = info["cost"]

                if success and outputs:
                    await create_transaction(
                        user_id=user_id, amount=0, balance_after=0,
                        transaction_type="deduction", reference_id=prompt_id,
                        description=f"完成: {info['prompt_name']} ({cost} 通证)",
                    )
                else:
                    await update_user_balance(user_id, cost)
                    await create_transaction(
                        user_id=user_id, amount=cost, balance_after=0,
                        transaction_type="refund", reference_id=prompt_id,
                        description=f"退款: 执行失败 ({info['prompt_name']})",
                    )
                logger.info(f"Billing finalized for prompt {prompt_id}: {'OK' if success else 'REFUND'} cost={cost}")
                completed_ids.append(prompt_id)

        for pid in completed_ids:
            _pb.pop(pid, None)
