"""ComfyUI Multi-Tenant Plugin — zero core modification.

Architecture:
- custom_nodes/comfyui_mt/__init__.py  — plugin entry (WEB_DIRECTORY + NODE hooks)
- custom_nodes/comfyui_mt/auth.py      — JWT auth (hmac/sha256, zero deps)
- custom_nodes/comfyui_mt/models.py    — SQLite models (users / workflows / previews)
- custom_nodes/comfyui_mt/routes.py    — aiohttp routes (auth / workflows / previews / admin)
- custom_nodes/comfyui_mt/middleware.py — auth guard + frontend injection
- custom_nodes/comfyui_mt/billing.py   — stub (reserved for future)
- custom_nodes/comfyui_mt/web/         — frontend extensions (auto-loaded by ComfyUI)

Design decisions:
- No billing (reserved stub only)
- No separate UI/page for users — everything in native ComfyUI interface
- Users see native ComfyUI with hidden: Models/Templates/Console/Settings
  (Settings button replaced with user menu)
- Admins see everything
- Workflows: Z&A (shared, admin-managed) / Custom (per-user, admin can manage all)
- Preview images persist across restart/refresh until workflow tab closed
"""
