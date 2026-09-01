"""Multi-tenant API routes — auth, workflows, previews, admin."""

import json
import logging
import os
from aiohttp import web

from .auth import hash_password, verify_password, create_token, get_user_from_request
from .models import (
    get_user, create_user, get_all_users, update_user,
    create_workflow, get_workflow, get_workflows_for_user, get_all_workflows,
    update_workflow, delete_workflow,
    save_preview_image, get_preview_images, delete_preview_images, cleanup_old_previews,
)
from .config import BILLING_ENABLED, PREVIEW_MAX_AGE, PREVIEW_MAX_SIZE_MB

logger = logging.getLogger(__name__)


def setup_api_routes(server):
    """Register all multi-tenant API routes."""

    # ── Diagnostic endpoint ──
    # Frontend posts runtime state here so we can see browser-side facts
    # (window.comfyAPI presence, api singleton, store state) in server logs.
    @server.routes.post("/api/mt/diag")
    async def diag(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            from .config import get_db_path
            diag_log = os.path.join(os.path.dirname(get_db_path()), "mt_diag.log")
        except Exception:
            diag_log = "/tmp/mt_diag.log"
        try:
            with open(diag_log, "a") as f:
                f.write(json.dumps(body, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return web.json_response({"status": "ok"})

    # ── Auth Routes ──

    @server.routes.post("/api/mt/auth/login")
    async def login(request):
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
        resp = web.json_response({
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "is_admin": bool(user["is_admin"]),
            },
        })
        # Set cookie so ComfyUI frontend axios requests are auto-authenticated
        import time as _time
        from .auth import TOKEN_EXPIRY as _TOKEN_EXPIRY
        resp.set_cookie(
            "mt_token", token,
            max_age=_TOKEN_EXPIRY,
            path="/",
            httponly=False,  # JS reads it for explicit headers too
            samesite="Lax",
        )
        return resp

    @server.routes.post("/api/mt/auth/register")
    async def register(request):
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
        )
        if not user:
            return web.json_response({"detail": "注册失败"}, status=500)

        return web.json_response({
            "id": user["id"],
            "username": user["username"],
            "message": "注册成功，请等待管理员激活账号"
        }, status=201)

    @server.routes.get("/api/mt/auth/me")
    async def get_me(request):
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)
        return web.json_response({
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "is_admin": bool(user["is_admin"]),
            "is_active": bool(user["is_active"]),
        })

    # ── Workflow Routes ──

    @server.routes.get("/api/mt/workflows")
    async def list_workflows(request):
        """List workflows visible to current user."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        workflows = await get_workflows_for_user(user["id"], include_za=True)
        return web.json_response({
            "items": [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "display_name": w["display_name"],
                    "description": w["description"],
                    "is_za": bool(w["is_za_workflow"]),
                    "owner_id": w["owner_id"],
                    "created_at": w["created_at"],
                    "updated_at": w["updated_at"],
                }
                for w in workflows
            ]
        })

    @server.routes.post("/api/mt/workflows")
    async def create_workflow_route(request):
        """Create a new workflow (custom or Z&A)."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        name = data.get("name", "").strip()
        workflow_data = data.get("workflow_data", {})
        display_name = data.get("display_name", "").strip() or name
        description = data.get("description", "").strip()
        is_za = bool(data.get("is_za", False))

        # Only admin can create Z&A workflows
        if is_za and not user["is_admin"]:
            return web.json_response({"detail": "只有管理员可以创建 Z&A 工作流"}, status=403)

        if not name:
            return web.json_response({"detail": "工作流名称不能为空"}, status=400)

        owner_id = None if is_za else user["id"]
        workflow = await create_workflow(
            name=name,
            workflow_data=workflow_data,
            owner_id=owner_id,
            display_name=display_name,
            description=description,
            is_za=is_za,
        )
        if not workflow:
            return web.json_response({"detail": "工作流名称已存在"}, status=409)

        # Sync Z&A workflow to all users' native workflow dirs (appears in browser)
        if is_za:
            try:
                from .isolation import sync_za_workflow_to_users
                sync_za_workflow_to_users(workflow_data, display_name)
            except Exception as e:
                logger.error(f"[ComfyUI-MT] Z&A file sync failed: {e}")

        return web.json_response(workflow, status=201)

    @server.routes.get("/api/mt/workflows/{workflow_id}")
    async def get_workflow_route(request):
        """Get a specific workflow."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        workflow_id = int(request.match_info["workflow_id"])
        workflow = await get_workflow(id=workflow_id)
        if not workflow:
            return web.json_response({"detail": "工作流不存在"}, status=404)

        # Check permission: owner, admin, or Z&A workflow
        if (workflow["owner_id"] != user["id"] and
            not user["is_admin"] and
            not workflow["is_za_workflow"]):
            return web.json_response({"detail": "无权访问"}, status=403)

        workflow["workflow_data"] = json.loads(workflow["workflow_data"])
        return web.json_response(workflow)

    @server.routes.put("/api/mt/workflows/{workflow_id}")
    async def update_workflow_route(request):
        """Update a workflow."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        workflow_id = int(request.match_info["workflow_id"])
        workflow = await get_workflow(id=workflow_id)
        if not workflow:
            return web.json_response({"detail": "工作流不存在"}, status=404)

        # Check permission
        if workflow["owner_id"] != user["id"] and not user["is_admin"]:
            return web.json_response({"detail": "无权修改"}, status=403)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        # Only admin can change is_za
        if "is_za" in data and not user["is_admin"]:
            del data["is_za"]

        success = await update_workflow(workflow_id, **data)
        if not success:
            return web.json_response({"detail": "更新失败"}, status=400)

        return web.json_response({"status": "updated"})

    @server.routes.delete("/api/mt/workflows/{workflow_id}")
    async def delete_workflow_route(request):
        """Delete a workflow."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        workflow_id = int(request.match_info["workflow_id"])
        workflow = await get_workflow(id=workflow_id)
        if not workflow:
            return web.json_response({"detail": "工作流不存在"}, status=404)

        # Check permission
        if workflow["owner_id"] != user["id"] and not user["is_admin"]:
            return web.json_response({"detail": "无权删除"}, status=403)

        # Remove Z&A workflow files from all users' native dirs
        if workflow["is_za_workflow"]:
            try:
                from .isolation import remove_za_workflow_from_users
                remove_za_workflow_from_users(workflow["display_name"])
            except Exception as e:
                logger.error(f"[ComfyUI-MT] Z&A file remove failed: {e}")

        await delete_workflow(workflow_id)
        return web.json_response({"status": "deleted"})

    # ── Preview Image Routes ──

    @server.routes.post("/api/mt/previews/save")
    async def save_preview(request):
        """Save a preview image reference."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        workflow_id = data.get("workflow_id", "")
        node_id = data.get("node_id", "")
        filename = data.get("filename", "")
        file_path = data.get("file_path", "")

        if not all([workflow_id, node_id, filename, file_path]):
            return web.json_response({"detail": "缺少必要参数"}, status=400)

        await save_preview_image(user["id"], workflow_id, node_id, filename, file_path)
        return web.json_response({"status": "saved"})

    @server.routes.get("/api/mt/previews/all")
    async def get_all_previews(request):
        """Get ALL persisted previews for the current user (for refresh restore)."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        from .models import _get_db
        db = _get_db()
        rows = db.execute(
            "SELECT * FROM preview_images WHERE user_id=? ORDER BY created_at DESC",
            (user["id"],)
        ).fetchall()
        return web.json_response({
            "items": [
                {
                    "workflow_id": r["workflow_id"],
                    "node_id": r["node_id"],
                    "filename": r["filename"],
                    "file_path": r["file_path"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        })

    @server.routes.get("/api/mt/previews/{workflow_id}")
    async def get_previews(request):
        """Get preview images for a workflow."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        workflow_id = request.match_info["workflow_id"]
        previews = await get_preview_images(user["id"], workflow_id)
        return web.json_response({"items": previews})

    @server.routes.get("/api/mt/previews/{workflow_id}/img/{filename}")
    async def get_preview_image(request):
        """Serve a persisted preview image file (auth required)."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        workflow_id = request.match_info["workflow_id"]
        filename = request.match_info["filename"]
        import urllib.parse
        filename = urllib.parse.unquote(filename)

        # Path safety: filename must be a bare filename (no path traversal)
        if "/" in filename or "\\" in filename or ".." in filename:
            return web.json_response({"detail": "Invalid filename"}, status=400)

        previews = await get_preview_images(user["id"], workflow_id)
        for p in previews:
            if p["filename"] == filename:
                try:
                    if not os.path.isfile(p["file_path"]):
                        return web.json_response({"detail": "文件不存在"}, status=404)
                    with open(p["file_path"], "rb") as f:
                        data = f.read()
                    import mimetypes
                    ctype = mimetypes.guess_type(filename)[0] or "image/png"
                    return web.Response(body=data, content_type=ctype)
                except Exception as e:
                    logger.error(f"[ComfyUI-MT] Preview image serve failed: {e}")
                    return web.json_response({"detail": "读取失败"}, status=500)

        return web.json_response({"detail": "预览图不存在"}, status=404)

    @server.routes.delete("/api/mt/previews/{workflow_id}")
    async def delete_previews(request):
        """Delete all preview images for a workflow (when tab closed)."""
        user = await get_user_from_request(request)
        if not user:
            return web.json_response({"detail": "未登录"}, status=401)

        workflow_id = request.match_info["workflow_id"]
        from .previews import cleanup_preview_files
        count = await cleanup_preview_files(user["id"], workflow_id)
        return web.json_response({"status": "deleted", "count": count})

    # ── Admin Routes ──

    async def _require_admin(request):
        user = await get_user_from_request(request)
        if not user:
            raise web.HTTPUnauthorized(
                body=json.dumps({"detail": "未登录"}),
                content_type="application/json"
            )
        if not user["is_admin"]:
            raise web.HTTPForbidden(
                body=json.dumps({"detail": "需要管理员权限"}),
                content_type="application/json"
            )
        return user

    @server.routes.get("/api/mt/admin/users")
    async def admin_list_users(request):
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
                    "is_admin": bool(u["is_admin"]),
                    "is_active": bool(u["is_active"]),
                    "created_at": u["created_at"],
                }
                for u in users
            ],
            "total": len(users),
        })

    @server.routes.post("/api/mt/admin/users/{user_id}/toggle-active")
    async def admin_toggle_user(request):
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        user_id = int(request.match_info["user_id"])
        user = await get_user(id=user_id)
        if not user:
            return web.json_response({"detail": "用户不存在"}, status=404)

        new_status = not user["is_active"]
        await update_user(user_id, is_active=new_status)
        return web.json_response({"status": "updated", "is_active": new_status})

    @server.routes.post("/api/mt/admin/users/{user_id}/role")
    async def admin_set_role(request):
        """Set user role (admin or normal)."""
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        user_id = int(request.match_info["user_id"])
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON"}, status=400)

        is_admin = bool(data.get("is_admin", False))

        # Prevent demoting the primary admin (username 15096756699)
        user = await get_user(id=user_id)
        if not user:
            return web.json_response({"detail": "用户不存在"}, status=404)
        if user["username"] == "15096756699" and not is_admin:
            return web.json_response({"detail": "不能取消主管理员的权限"}, status=400)

        await update_user(user_id, is_admin=is_admin)
        return web.json_response({"status": "updated", "is_admin": is_admin})

    @server.routes.get("/api/mt/admin/workflows")
    async def admin_list_workflows(request):
        try:
            await _require_admin(request)
        except web.HTTPException as e:
            return e

        workflows = await get_all_workflows()
        # Resolve owner usernames
        owner_names = {}
        all_users = await get_all_users()
        for u in all_users:
            owner_names[u["id"]] = u["username"]
        return web.json_response({
            "items": [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "display_name": w["display_name"],
                    "description": w["description"],
                    "is_za": bool(w["is_za_workflow"]),
                    "owner_id": w["owner_id"],
                    "owner_username": owner_names.get(w["owner_id"], "—") if w["owner_id"] else None,
                    "created_at": w["created_at"],
                    "updated_at": w["updated_at"],
                }
                for w in workflows
            ]
        })

    # ── Health Check ──

    @server.routes.get("/api/mt/health")
    async def health_check(request):
        return web.json_response({
            "status": "ok",
            "billing_enabled": BILLING_ENABLED,
            "preview_max_age": PREVIEW_MAX_AGE,
            "preview_max_size_mb": PREVIEW_MAX_SIZE_MB,
        })

    logger.info("[ComfyUI-MT] API routes registered")
