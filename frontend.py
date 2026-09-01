"""Frontend injection — login page + ComfyUI UI overrides."""

import json
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


def get_login_page_html() -> str:
    """Return the login page HTML (self-contained, no external deps)."""
    return """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Z&A UI</title><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans SC",sans-serif;min-height:100vh;background:linear-gradient(135deg,#0f0f13 0%,#1a1d23 40%,#25262b 100%);display:flex;align-items:center;justify-content:center;overflow:hidden}
.bg-grid{position:fixed;inset:0;background-image:linear-gradient(rgba(255,255,255,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.03) 1px,transparent 1px);background-size:60px 60px;z-index:0}
.bg-glow{position:fixed;inset:0;background:radial-gradient(ellipse 600px 400px at 50% 40%,rgba(79,110,247,0.12) 0%,transparent 70%);z-index:0}
.login-card{position:relative;z-index:2;width:100%;max-width:420px;padding:40px 36px 32px;background:#1c1e24;border:1px solid rgba(255,255,255,0.08);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,0.5)}
.login-card h1{text-align:center;font-size:22px;font-weight:700;color:#fff;margin-bottom:4px}
.login-card .sub{text-align:center;color:#667085;font-size:13px;margin-bottom:28px}
.tab-bar{display:flex;margin-bottom:24px;border-bottom:1px solid rgba(255,255,255,0.08)}
.tab-btn{flex:1;padding:10px;text-align:center;font-size:14px;font-weight:500;color:#667085;cursor:pointer;border-bottom:2px solid transparent;transition:all 0.15s;background:none;border:none}
.tab-btn:hover{color:#c4c7d0}.tab-btn.active{color:#4f6ef7;border-bottom-color:#4f6ef7}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:13px;font-weight:500;color:#c4c7d0;margin-bottom:6px}
.form-group input{width:100%;padding:10px 14px;border:1px solid rgba(255,255,255,0.1);border-radius:8px;background:#141518;color:#fff;font-size:14px;outline:none}
.form-group input:focus{border-color:#4f6ef7}
.form-group input::placeholder{color:#4a4d57}
.submit-btn{width:100%;padding:11px;margin-top:4px;background:linear-gradient(135deg,#4f6ef7 0%,#6c5ce7 100%);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
.submit-btn:hover{opacity:0.9}.submit-btn:disabled{opacity:0.5;cursor:not-allowed}
.error-msg{color:#ef4444;font-size:13px;margin-top:8px;display:none;text-align:center}
.success-msg{color:#10b981;font-size:13px;margin-top:8px;display:none;text-align:center}
.form-panel{display:none}.form-panel.active{display:block}
.footer-text{text-align:center;margin-top:20px;font-size:13px;color:#4a4d57}
</style></head><body>
<div class="bg-grid"></div><div class="bg-glow"></div>
<div class="login-card">
<h1>Z&A UI</h1><p class="sub">登录以使用工作台</p>
<div class="tab-bar"><button class="tab-btn active" data-tab="login" onclick="switchTab('login')">登录</button><button class="tab-btn" data-tab="register" onclick="switchTab('register')">注册</button></div>
<div id="panel-login" class="form-panel active">
<div class="form-group"><label>用户名</label><input id="mt-u" placeholder="输入用户名" autocomplete="username"></div>
<div class="form-group"><label>密码</label><input id="mt-p" type="password" placeholder="输入密码" autocomplete="current-password" onkeydown="if(event.key==='Enter')doLogin()"></div>
<button class="submit-btn" id="mt-btn" onclick="doLogin()">登录</button><div id="mt-err" class="error-msg"></div></div>
<div id="panel-register" class="form-panel">
<div class="form-group"><label>用户名</label><input id="reg-u" placeholder="输入用户名" autocomplete="username"></div>
<div class="form-group"><label>显示名称</label><input id="reg-n" placeholder="输入显示名称（可选）" autocomplete="nickname"></div>
<div class="form-group"><label>密码</label><input id="reg-p" type="password" placeholder="至少6位密码" autocomplete="new-password"></div>
<button class="submit-btn" id="reg-btn" onclick="doRegister()">注册</button><div id="reg-err" class="error-msg"></div><div id="reg-ok" class="success-msg"></div></div>
<div class="footer-text">注册后需管理员激活账号</div>
</div>
<script>
const API = '/api/mt';
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.form-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tab));
}
async function doLogin() {
  const u = document.getElementById('mt-u').value.trim();
  const p = document.getElementById('mt-p').value;
  const err = document.getElementById('mt-err');
  const btn = document.getElementById('mt-btn');
  if (!u || !p) { err.textContent = '请输入用户名和密码'; err.style.display = 'block'; return; }
  btn.disabled = true; btn.textContent = '登录中...';
  try {
    const r = await fetch(API + '/auth/login', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: u, password: p}) });
    const d = await r.json();
    if (r.ok) {
      // Clear ComfyUI's per-user workflow/tab/draft state BEFORE switching
      // user, so the previous account's open workflows don't leak into the
      // new account's canvas. These keys (Comfy.Workflow.*) are NOT scoped
      // by account — they persist across login/logout in the same browser.
      clearWorkflowState();
      // Restore THIS account's own workflow state (drafts + open tabs) that
      // was snapshotted at logout, so each user keeps their own storage.
      try {
        const saved = localStorage.getItem('mt_wf_state:' + d.user.id);
        if (saved) restoreWorkflowState(JSON.parse(saved));
      } catch(e) {}
      localStorage.setItem('mt_token', d.access_token);
      localStorage.setItem('mt_user', JSON.stringify(d.user));
      window.location.href = '/';
    } else { err.textContent = d.detail || '登录失败'; err.style.display = 'block'; }
  } catch(e) { err.textContent = '网络错误'; err.style.display = 'block'; }
  btn.disabled = false; btn.textContent = '登录';
}
// Remove ComfyUI workflow/tab/draft pointers so a fresh login starts clean.
// Keys: Comfy.Workflow.{OpenPaths,ActivePath,LastOpenPaths,LastActivePath,
//        DraftIndex.v2,Draft.v2} (scoped by clientId/workspace, NOT by user).
function clearWorkflowState() {
  const prefixes = [
    'Comfy.Workflow.OpenPaths:',
    'Comfy.Workflow.ActivePath:',
    'Comfy.Workflow.LastOpenPaths:',
    'Comfy.Workflow.LastActivePath:',
    'Comfy.Workflow.DraftIndex.v2:',
    'Comfy.Workflow.Draft.v2:'
  ];
  function sweep(store) {
    if (!store) return;
    try {
      const keys = [];
      for (let i = 0; i < store.length; i++) keys.push(store.key(i));
      for (const k of keys) {
        if (!k) continue;
        for (const p of prefixes) {
          if (k.indexOf(p) === 0) { store.removeItem(k); break; }
        }
      }
    } catch(e) {}
  }
  sweep(window.localStorage);
  sweep(window.sessionStorage);
}
// Restore a per-account workflow-state snapshot into storage.
function restoreWorkflowState(snap) {
  if (!snap) return;
  function write(store, obj) {
    if (!store) return;
    for (const k of Object.keys(obj || {})) {
      try { store.setItem(k, obj[k]); } catch(e) {}
    }
  }
  write(window.localStorage, snap.local);
  write(window.sessionStorage, snap.session);
}
async function doRegister() {
  const u = document.getElementById('reg-u').value.trim();
  const n = document.getElementById('reg-n').value.trim();
  const p = document.getElementById('reg-p').value;
  const err = document.getElementById('reg-err');
  const ok = document.getElementById('reg-ok');
  const btn = document.getElementById('reg-btn');
  if (!u || !p) { err.textContent = '请输入用户名和密码'; err.style.display = 'block'; return; }
  btn.disabled = true; btn.textContent = '注册中...';
  try {
    const r = await fetch(API + '/auth/register', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: u, password: p, display_name: n || u}) });
    const d = await r.json();
    if (r.ok) { ok.textContent = d.message || '注册成功，请等待管理员激活'; ok.style.display = 'block'; err.style.display = 'none'; }
    else { err.textContent = d.detail || '注册失败'; err.style.display = 'block'; ok.style.display = 'none'; }
  } catch(e) { err.textContent = '网络错误'; err.style.display = 'block'; }
  btn.disabled = false; btn.textContent = '注册';
}
// Auto-login if token exists
const token = localStorage.getItem('mt_token');
if (token) { window.location.href = '/?token=' + encodeURIComponent(token); }
</script></body></html>"""


def get_frontend_extension_js() -> str:
    """Return the frontend extension JS that modifies ComfyUI's UI.

    This is auto-loaded by ComfyUI from web/ directory.
    It handles:
    - Hiding Models/Templates/Console/Settings for non-admin users
    - Replacing Settings with user menu
    - Adding workflow type indicators (Z&A vs Custom)
    - Preview image persistence hooks
    """
    return """
// ComfyUI Multi-Tenant Frontend Extension
// Auto-loaded by ComfyUI from web/ directory

(function() {
  'use strict';

  const MT_API = '/api/mt';
  let mtUser = null;
  let mtToken = localStorage.getItem('mt_token');

  // ── Auth Helpers ──
  function getAuthHeaders() {
    return mtToken ? { 'Authorization': 'Bearer ' + mtToken } : {};
  }

  async function fetchUser() {
    if (!mtToken) return null;
    try {
      const r = await fetch(MT_API + '/auth/me', { headers: getAuthHeaders() });
      if (r.ok) {
        mtUser = await r.json();
        localStorage.setItem('mt_user', JSON.stringify(mtUser));
        return mtUser;
      } else {
        // Token expired
        localStorage.removeItem('mt_token');
        localStorage.removeItem('mt_user');
        mtToken = null;
        window.location.reload();
      }
    } catch(e) { console.error('[MT] fetchUser error:', e); }
    return null;
  }

  // ── UI Overrides ──
  function hideFeaturesForUser() {
    if (!mtUser || mtUser.is_admin) return;

    // Hide left panel buttons: Models, Templates, Console, Settings
    // ComfyUI's new UI uses [data-testid] or class-based selectors
    const hideSelectors = [
      '[data-testid="models-button"]',
      '[data-testid="templates-button"]',
      '[data-testid="console-button"]',
      '.comfyui-menu-models',
      '.comfyui-menu-templates',
      '.comfyui-menu-console',
      // Settings button — we'll replace it
      '[data-testid="settings-button"]',
      '.comfyui-menu-settings',
    ];

    hideSelectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = 'none';
      });
    });

    // Hide ComfyUI Manager button (top right)
    const managerSelectors = [
      '[data-testid="manager-button"]',
      '.comfyui-manager-button',
      '#comfyui-manager-button',
    ];
    managerSelectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = 'none';
      });
    });

    // Add user menu in place of settings
    addUserMenu();
  }

  function addUserMenu() {
    // Find the settings button location and add user menu nearby
    const topBar = document.querySelector('.comfyui-menu, .comfy-menu, header, [class*="toolbar"]');
    if (!topBar) return;

    const userBtn = document.createElement('button');
    userBtn.className = 'mt-user-btn';
    userBtn.innerHTML = '<span>👤</span> ' + (mtUser?.display_name || mtUser?.username || 'User');
    userBtn.style.cssText = 'padding:6px 12px;background:#2a2d35;border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#c4c7d0;font-size:13px;cursor:pointer;';
    userBtn.onclick = showUserMenu;

    // Try to insert near settings
    const settingsBtn = document.querySelector('[data-testid="settings-button"], .comfyui-menu-settings');
    if (settingsBtn && settingsBtn.parentNode) {
      settingsBtn.parentNode.insertBefore(userBtn, settingsBtn);
      settingsBtn.style.display = 'none';
    } else {
      topBar.appendChild(userBtn);
    }
  }

  function showUserMenu() {
    // Simple dropdown with logout
    const existing = document.querySelector('.mt-user-menu');
    if (existing) { existing.remove(); return; }

    const menu = document.createElement('div');
    menu.className = 'mt-user-menu';
    menu.style.cssText = 'position:absolute;top:100%;right:0;margin-top:4px;background:#1c1e24;border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:8px 0;min-width:160px;z-index:10000;box-shadow:0 8px 24px rgba(0,0,0,0.4);';
    menu.innerHTML = `
      <div style="padding:8px 16px;font-size:13px;color:#667085;border-bottom:1px solid rgba(255,255,255,0.08);">
        ${mtUser?.display_name || mtUser?.username || 'User'}
        ${mtUser?.is_admin ? '<span style="color:#4f6ef7;font-size:11px;margin-left:4px;">Admin</span>' : ''}
      </div>
      <button onclick="mtLogout()" style="width:100%;padding:8px 16px;text-align:left;background:none;border:none;color:#c4c7d0;font-size:13px;cursor:pointer;">退出登录</button>
    `;

    const btn = document.querySelector('.mt-user-btn');
    if (btn) {
      btn.style.position = 'relative';
      btn.appendChild(menu);
    }

    // Close on click outside
    setTimeout(() => {
      document.addEventListener('click', function closeMenu(e) {
        if (!menu.contains(e.target) && e.target !== btn) {
          menu.remove();
          document.removeEventListener('click', closeMenu);
        }
      });
    }, 0);
  }

  window.mtLogout = function() {
    localStorage.removeItem('mt_token');
    localStorage.removeItem('mt_user');
    window.location.reload();
  };

  // ── Workflow Type Indicators ──
  function addWorkflowIndicators() {
    // Add badge to workflow tabs showing Z&A or Custom
    // This hooks into ComfyUI's workflow tab system
    const observer = new MutationObserver(() => {
      document.querySelectorAll('.workflow-tab, [class*="workflow-tab"]').forEach(tab => {
        if (tab.querySelector('.mt-wf-badge')) return;
        const badge = document.createElement('span');
        badge.className = 'mt-wf-badge';
        badge.style.cssText = 'font-size:10px;padding:1px 4px;border-radius:3px;margin-left:4px;';
        // Determine if Z&A or Custom based on workflow data
        // This is a placeholder — actual logic depends on how workflows are loaded
        badge.textContent = '自定义';
        badge.style.background = '#2a2d35';
        badge.style.color = '#9ca3af';
        tab.appendChild(badge);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // ── Preview Image Persistence ──
  // Hook into PreviewImage node to save/load images from server
  function setupPreviewPersistence() {
    // This will be implemented via ComfyUI's node extension API
    // For now, we rely on the backend to save/serve preview images
    console.log('[MT] Preview persistence ready');
  }

  // ── Initialization ──
  async function init() {
    // Check if we're on the login page
    if (document.querySelector('.login-card')) return;

    // Fetch user info
    await fetchUser();
    if (!mtUser) {
      // Not logged in — middleware should have redirected, but just in case
      window.location.reload();
      return;
    }

    // Apply UI overrides
    hideFeaturesForUser();
    addWorkflowIndicators();
    setupPreviewPersistence();

    console.log('[MT] Multi-tenant UI initialized for:', mtUser.username, mtUser.is_admin ? '(admin)' : '(user)');
  }

  // Wait for ComfyUI to load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""
