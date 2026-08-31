# ComfyUI-MT Plugin Architecture

## Overview

Zero-core-modification multi-tenant plugin for ComfyUI. Lives in `custom_nodes/comfyui_mt/`.

## Key Design Decisions

1. **No core modification**: Pure custom_node plugin. Official ComfyUI can be updated independently.
2. **V3 Extension API**: Uses `comfy_entrypoint()` returning `ComfyExtension` subclass.
3. **No separate UI**: Users see native ComfyUI with hidden features. Admin sees everything.
4. **Billing reserved**: Stub only (`MT_BILLING=1` to enable). No token/balance logic active.
5. **Preview persistence**: DB tracks preview images per user/workflow/node. Survives restart/refresh.

## File Structure

```
custom_nodes/comfyui_mt/
├── __init__.py          # V3 Extension entry point (comfy_entrypoint)
├── auth.py              # JWT auth (hmac/sha256, zero deps)
├── models.py            # SQLite models (users / workflows / preview_images)
├── routes.py            # API routes (/api/mt/*)
├── middleware.py        # Auth guard middleware (protects /api/*, serves login page)
├── frontend.py          # Login page HTML + frontend extension JS
├── config.py            # Configuration (DB path, feature flags)
├── billing.py           # Stub for future billing
└── web/                 # Frontend extensions (auto-loaded by ComfyUI)
    ├── mt_extension.js  # UI overrides (hide features, user menu, workflow badges)
    └── mt_style.css     # Extension styles
```

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/mt/auth/login` | POST | No | Login, returns JWT |
| `/api/mt/auth/register` | POST | No | Register (inactive until admin approves) |
| `/api/mt/auth/me` | GET | Yes | Current user info |
| `/api/mt/workflows` | GET/POST | Yes | List/create workflows |
| `/api/mt/workflows/{id}` | GET/PUT/DELETE | Yes | Workflow CRUD |
| `/api/mt/previews/save` | POST | Yes | Save preview image ref |
| `/api/mt/previews/{wf_id}` | GET/DELETE | Yes | Get/clear workflow previews |
| `/api/mt/admin/users` | GET | Admin | List all users |
| `/api/mt/admin/users/{id}/toggle-active` | POST | Admin | Enable/disable user |
| `/api/mt/admin/workflows` | GET | Admin | List all workflows |
| `/api/mt/health` | GET | No | Health check |

## Database Schema

```sql
users: id, username, password_hash, display_name, is_admin, is_active, created_at
workflows: id, name, display_name, description, workflow_data, is_za_workflow, owner_id, created_at, updated_at
preview_images: id, user_id, workflow_id, node_id, filename, file_path, created_at
```

## Frontend Extension

Auto-loaded by ComfyUI from `web/` directory. Handles:
- Hide Models/Templates/Console/Settings for non-admin users
- Replace Settings with user menu (👤 username)
- Hide ComfyUI Manager button for non-admin
- Add workflow type badges (Z&A / 自定义)
- Preview persistence hooks (save/restore on workflow open/close)

## Admin Account

- Username: `15096756699`
- Password: `crd240108162`
- Created automatically on first run

## Deployment

1. Clone official ComfyUI: `git clone https://github.com/comfyanonymous/ComfyUI.git`
2. Copy plugin to `custom_nodes/comfyui_mt/`
3. Start: `python main.py --listen 0.0.0.0 --port 8188`
4. Access: `http://<ip>:8188`

## Known Limitations / TODO

- Preview persistence: backend DB ready, frontend hooks need ComfyUI node extension API integration
- Workflow badges: placeholder logic, needs workflow type detection from loaded workflow data
- Billing: stub only, no actual cost calculation
- Admin panel: no separate UI, managed via API only (future: add to user menu for admin)
