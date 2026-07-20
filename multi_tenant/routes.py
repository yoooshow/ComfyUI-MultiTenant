"""Multi-tenant API routes."""

import json
import logging
import os

from aiohttp import web
from aiohttp.multipart import MultipartReader

from .models import (
    get_user, create_user, update_user_balance,
    create_transaction, get_transactions, get_all_users,
    get_all_transactions, get_stats,
    create_workflow_template, get_workflow_templates, delete_workflow_template,
)
from .auth import hash_password, verify_password, create_token, get_user_from_request
from .frontend import inject_frontend

logger = logging.getLogger(__name__)


def setup_routes(server):
    """Register multi-tenant API routes on the PromptServer."""

    @server.routes.post("/api/auth/login")
    async def login(request):
        """Authenticate and return a JWT token."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        username = data.get("username", "")
        password = data.get("password", "")

        if not username or not password:
            return web.json_response({"detail": "用户名和密码不能为空"}, status=400)

        user = await get_user(username=username)
        if not user or not verify_password(password, user["password_hash"]):
            return web.json_response({"detail": "用户名或密码错误"}, status=401)

        if not user["is_active"]:
            return web.json_response({"detail": "用户已被禁用"}, status=403)

        token = create_token(user["id"], user["username"])
        return web.json_response({
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "token_balance": user["token_balance"],
                "is_admin": bool(user["is_admin"]),
            },
        })

    @server.routes.post("/api/auth/register")
    async def register(request):
        """Register a new user."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        username = data.get("username", "").strip()
        password = data.get("password", "")
        display_name = data.get("display_name", "").strip() or username

        if len(username) < 3:
            return web.json_response({"detail": "用户名至少3个字符"}, status=400)
        if len(password) < 6:
            return web.json_response({"detail": "密码至少6个字符"}, status=400)

        existing = await get_user(username=username)
        if existing:
            return web.json_response({"detail": "用户名已存在"}, status=409)

        user = await create_user(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            token_balance=100,  # Default welcome tokens
        )
        if not user:
            return web.json_response({"detail": "注册失败"}, status=500)

        token = create_token(user["id"], user["username"])
        return web.json_response({
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "token_balance": user["token_balance"],
                "is_admin": bool(user["is_admin"]),
            },
        }, status=201)

    @server.routes.get("/api/auth/me")
    async def get_me(request):
        """Get current user info."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)
        return web.json_response({
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "token_balance": user["token_balance"],
            "is_admin": bool(user["is_admin"]),
            "is_active": bool(user["is_active"]),
        })

    @server.routes.get("/api/users/me/balance")
    async def get_balance(request):
        """Get current user's token balance."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)
        return web.json_response({
            "token_balance": user["token_balance"],
        })

    @server.routes.get("/api/users/me/transactions")
    async def list_transactions(request):
        """Get current user's transaction history."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        page = int(request.query.get("page", 1))
        page_size = int(request.query.get("page_size", 20))
        offset = (page - 1) * page_size

        txns = await get_transactions(user["id"], limit=page_size, offset=offset)
        return web.json_response({
            "items": [
                {
                    "id": t["id"],
                    "amount": t["amount"],
                    "balance_after": t["balance_after"],
                    "transaction_type": t["transaction_type"],
                    "description": t["description"],
                    "created_at": t["created_at"],
                }
                for t in txns
            ],
        })

    @server.routes.post("/api/workspace/execute")
    async def execute_workflow(request):
        """Queue a workflow for execution. Bill is handled by the prompt wrapper."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "请先登录"}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        workflow_data = data.get("workflow_data")
        if not workflow_data:
            return web.json_response({"detail": "No workflow data"}, status=400)

        # Forward to ComfyUI's internal prompt endpoint
        from .billing import calculate_cost
        cost = calculate_cost({"prompt": workflow_data}, user=user)

        if user["token_balance"] < cost:
            return web.json_response({
                "detail": f"通证不足 (需要 {cost}, 当前 {user['token_balance']})"
            }, status=402)

        # Deduct tokens
        await update_user_balance(user["id"], -cost)
        await create_transaction(
            user_id=user["id"],
            amount=-cost,
            balance_after=user["token_balance"] - cost,
            transaction_type="deduction_hold",
            reference_id="execute_api",
            description=f"执行工作流 ({cost} 通证)",
        )

        import time
        import uuid
        from .config import pending_bills as _pending_bills
        session_id = str(uuid.uuid4())
        _pending_bills[session_id] = {
            "user_id": user["id"],
            "cost": cost,
            "prompt_name": data.get("workflow_name", "unknown"),
            "start_time": time.time(),
        }


        return web.json_response({
            "status": "queued",
            "prompt_id": prompt_id,
            "token_cost": cost,
            "token_balance": user["token_balance"] - cost,
        })

    # ── Admin Routes ──

    async def _require_admin(request):
        """Check that the request is from an admin user."""
            "session_id": session_id,
            "prompt_id": session_id,
        if not user:
            raise web.HTTPUnauthorized(body=json.dumps({"detail": "未登录"}),
                                       content_type="application/json")
        if not user["is_admin"]:
            raise web.HTTPForbidden(body=json.dumps({"detail": "需要管理员权限"}),
                                    content_type="application/json")
        return user

    @server.routes.get("/api/admin/users")
    async def admin_list_users(request):
        """List all users (admin only)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        users = await get_all_users()
        return web.json_response({
            "items": [
                {
                    "id": u["id"],
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "token_balance": u["token_balance"],
                    "is_admin": bool(u["is_admin"]),
                    "is_active": bool(u["is_active"]),
                    "created_at": u["created_at"],
                }
                for u in users
            ],
            "total": len(users),
        })

    @server.routes.post("/api/admin/users")
    async def admin_create_user(request):
        """Create a user (admin only)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        username = data.get("username", "").strip()
        password = data.get("password", "")
        display_name = data.get("display_name", "").strip() or username
        token_balance = int(data.get("token_balance", 0))
        is_admin = bool(data.get("is_admin", False))

        if not username or not password:
            return web.json_response({"detail": "用户名和密码不能为空"}, status=400)

        existing = await get_user(username=username)
        if existing:
            return web.json_response({"detail": "用户名已存在"}, status=409)

        user = await create_user(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            token_balance=token_balance,
            is_admin=is_admin,
        )
        if not user:
            return web.json_response({"detail": "创建失败"}, status=500)

        return web.json_response({
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "token_balance": user["token_balance"],
            "is_admin": bool(user["is_admin"]),
        }, status=201)

    @server.routes.post("/api/admin/users/{user_id}/tokens")
    async def admin_adjust_tokens(request):
        """Adjust a user's token balance (admin only)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        user_id = int(request.match_info["user_id"])
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        amount = int(data.get("amount", 0))

        # Get current user
        user = await get_user(id=user_id)
        if not user:
            return web.json_response({"detail": "用户不存在"}, status=404)

        if amount > 0:
            await update_user_balance(user_id, amount)
            await create_transaction(
                user_id=user_id,
                amount=amount,
                balance_after=user["token_balance"] + amount,
                transaction_type="admin_adjust",
                reference_id="admin",
                description=data.get("description", f"管理员调整 +{amount}"),
            )
        elif amount < 0:
            success = await update_user_balance(user_id, amount)
            if not success:
                return web.json_response({"detail": "余额不足"}, status=400)
            await create_transaction(
                user_id=user_id,
                amount=amount,
                balance_after=max(0, user["token_balance"] + amount),
                transaction_type="admin_adjust",
                reference_id="admin",
                description=data.get("description", f"管理员调整 {amount}"),
            )

        updated_user = await get_user(id=user_id)
        return web.json_response({
            "token_balance": updated_user["token_balance"] if updated_user else 0,
        })

    @server.routes.get("/api/admin/stats")
    async def admin_stats(request):
        """Get system statistics (admin only)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        stats = await get_stats()
        return web.json_response(stats)

    # ── Workflow Template Routes (public / admin) ──

    @server.routes.get("/api/jobs/workflows")
    async def list_public_workflows(request):
        """List active workflow templates."""
        templates = await get_workflow_templates(active_only=True)
        return web.json_response([
            {
                "id": t["id"],
                "name": t["name"],
                "display_name": t["display_name"],
                "description": t["description"],
                "comfyui_workflow": t.get("comfyui_workflow", {}),
                "base_cost": t["base_cost"],
                "cost_per_step": t["cost_per_step"],
                "cost_per_megapixel": t["cost_per_megapixel"],
                "is_active": bool(t["is_active"]),
            }
            for t in templates
        ])

    @server.routes.get("/api/admin/workflows")
    async def admin_list_workflows(request):
        """List all workflow templates (admin only)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        templates = await get_workflow_templates(active_only=False)
        return web.json_response([
            {
                "id": t["id"],
                "name": t["name"],
                "display_name": t["display_name"],
                "description": t["description"],
                "comfyui_workflow": t.get("comfyui_workflow", {}),
                "base_cost": t["base_cost"],
                "cost_per_step": t["cost_per_step"],
                "cost_per_megapixel": t["cost_per_megapixel"],
                "is_active": bool(t["is_active"]),
                "created_at": t["created_at"],
            }
            for t in templates
        ])

    @server.routes.post("/api/admin/workflows")
    async def admin_create_workflow(request):
        """Upload a workflow template (admin only)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        # Parse from either JSON body or file upload
        content_type = request.content_type or ""

        if "multipart/form-data" in content_type:
            # File upload
            reader = MultipartReader.from_response(request)
            workflow_data = {}
            name = ""
            display_name = ""

            async for part in reader:
                if part.name == "file":
                    content = await part.read()
                    try:
                        workflow_data = json.loads(content)
                    except json.JSONDecodeError:
                        return web.json_response({"detail": "无效的 JSON 格式"}, status=400)
                    # Use filename as name
                    filename = part.filename or "workflow.json"
                    name = os.path.splitext(filename)[0]
                    display_name = name

        else:
            # JSON body
            try:
                data = await request.json()
            except Exception:
                return web.json_response({"detail": "Invalid JSON"}, status=400)
            name = data.get("name", "")
            display_name = data.get("display_name", name)
            description = data.get("description", "")
            workflow_data = data.get("comfyui_workflow", data)
            base_cost = int(data.get("base_cost", 10))
            cost_per_step = int(data.get("cost_per_step", 1))
            cost_per_megapixel = int(data.get("cost_per_megapixel", 5))

        if not name or not workflow_data:
            return web.json_response({"detail": "请提供工作流名称和数据"}, status=400)

        result = await create_workflow_template(
            name=name,
            display_name=display_name or name,
            comfyui_workflow=workflow_data,
            description=description if "description" in locals() else "",
            base_cost=base_cost if "base_cost" in locals() else 10,
            cost_per_step=cost_per_step if "cost_per_step" in locals() else 1,
            cost_per_megapixel=cost_per_megapixel if "cost_per_megapixel" in locals() else 5,
        )
        if not result:
            return web.json_response({"detail": "创建失败，名称可能已存在"}, status=409)

        return web.json_response(result, status=201)

    @server.routes.delete("/api/admin/workflows/{template_id}")
    async def admin_delete_workflow(request):
        """Delete a workflow template (admin only)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        template_id = int(request.match_info["template_id"])
        if await delete_workflow_template(template_id):
            return web.json_response({"status": "deleted"})
        return web.json_response({"detail": "模板不存在"}, status=404)

    # ── Health Endpoint ──

    @server.routes.get("/api/health")
    async def health_check(request):
        """Health check endpoint."""
        from .config import pending_bills as _pending_bills
        return web.json_response({
            "status": "ok",
            "pending_bills": len(_pending_bills),
        })

    # ── Frontend Injection ──
    # Inject our login UI and lock script into ComfyUI's frontend
    async def handle_track_prompt(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response([error, Invalid JSON], status=400)
        session_id = data.get("session_id", "")
        real_prompt_id = data.get("prompt_id", "")
        if not session_id or not real_prompt_id:
            return web.json_response([error, Missing fields], status=400)
        from .auth import get_user_from_request as gur
        user = await gur(request)
        if not user:
            return web.json_response([error, Unauthorized], status=401)
        from .config import pending_bills as _pb
        if session_id in _pb:
            _pb[real_prompt_id] = _pb.pop(session_id)
            logger.info(Tracked  + real_prompt_id)
            return web.json_response([ok, tracked], status=200)
        return web.json_response([ok, not_found], status=200)
    endpoints_registered.append("/api/workspace/track-prompt POST")
    server.app.router.add_post("/api/workspace/track-prompt", handle_track_prompt)

    inject_frontend(server)

    logger.info(f"Registered {len(server.routes)} routes including multi-tenant endpoints")
