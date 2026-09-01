// ComfyUI Multi-Tenant Frontend Extension v3
// Auto-loaded by ComfyUI from web/ directory.
// Strategy: never touch DOM at module top-level (ComfyUI dynamic-imports
// extensions before Vue mounts). All DOM work happens after init() on
// DOMContentLoaded + MutationObserver retry. User menu mounts at the
// bottom of the native sidebar account area (does NOT replace Settings).

(function() {
  'use strict';

  // ── Loaded marker ──
  try {
    document.title = '[MT-LOADED v47]';
  } catch(e) {}

  // NOTE: do NOT bootstrap previews from localStorage here. The previous
  // mt_previews_cache was a SINGLE global key shared across ALL accounts —
  // switching user leaked the previous account's previews into the new
  // account's canvas (user: "换账号后预览图还在"). Per-user restore is done
  // exclusively through the authenticated /previews/all API (server filters
  // by user_id), so drop the local cache entirely.

  const MT_API = '/api/mt';
  let mtUser = null;
  let mtToken = null;
  let hideApplied = false;
  let menuMounted = false;
  let bootMarker = null;

  // ── Boot marker (diagnostic; only added once DOM exists) ──
  function addBootMarker(text) {
    try {
      if (!bootMarker) {
        bootMarker = document.createElement('div');
        bootMarker.id = 'mt-boot-marker';
        bootMarker.style.cssText = 'position:fixed;top:0;left:0;z-index:99999;background:#4f6ef7;color:#fff;font-size:10px;padding:2px 6px;border-radius:0 0 4px 0;pointer-events:none;';
        document.documentElement.appendChild(bootMarker);
      }
      bootMarker.textContent = text;
    } catch(e) {}
  }

  // ── Diagnostics ──
  // Write to both document.title AND the fixed boot marker element so we can
  // always see the latest state even when ComfyUI overwrites the title.
  function setDiag(text) {
    try { document.title = '[MT] ' + text; } catch(e) {}
    try {
      let m = document.getElementById('mt-boot-marker');
      if (!m) {
        m = document.createElement('div');
        m.id = 'mt-boot-marker';
        m.style.cssText = 'position:fixed;top:0;left:0;z-index:99999;background:#4f6ef7;color:#fff;font-size:11px;padding:3px 8px;border-radius:0 0 4px 0;pointer-events:none;font-family:monospace;';
        document.documentElement.appendChild(m);
      }
      m.textContent = '[MT] ' + text;
    } catch(e) {}
  }

  // ── Auth Helpers ──
  function getCookie(name) {
    try {
      const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
      return m ? decodeURIComponent(m[1]) : '';
    } catch(e) { return ''; }
  }

  function getToken() {
    if (mtToken) return mtToken;
    try { mtToken = localStorage.getItem('mt_token') || ''; } catch(e) { mtToken = ''; }
    if (!mtToken) mtToken = getCookie('mt_token') || '';
    return mtToken;
  }

  function getAuthHeaders() {
    const t = getToken();
    return t ? { 'Authorization': 'Bearer ' + t } : {};
  }

  async function fetchUser() {
    const t = getToken();
    if (!t) return null;
    try {
      const r = await fetch(MT_API + '/auth/me', { headers: getAuthHeaders() });
      if (r.ok) {
        mtUser = await r.json();
        try { localStorage.setItem('mt_user', JSON.stringify(mtUser)); } catch(e) {}
        return mtUser;
      } else {
        // Token invalid — let middleware redirect to login page on next nav
        try {
          localStorage.removeItem('mt_token');
          localStorage.removeItem('mt_user');
        } catch(e) {}
        mtToken = '';
        return null;
      }
    } catch(e) {
      console.error('[MT] fetchUser error:', e);
      return null;
    }
  }

  // ── UI Overrides ──
  // Non-admin users see a restricted sidebar. Admin sees everything.
  const HIDDEN_SELECTORS = [
    '[data-testid="model-library-tab-button"]', // 模型库
    '.templates-tab-button',                    // 模板
    '.side-bar-button-icon[class*="ph--terminal-bold"]', // 控制台
    '.side-bar-button-icon[class*="lucide--keyboard"]',  // 快捷键
    '.comfyui-manager-button',                  // ComfyUI Manager
    '[data-testid="manager-button"]',
    '.manager-button',
    '#comfyui-manager-button',
    '[class*="manager"][class*="button"]',
  ];

  function applyHidden() {
    HIDDEN_SELECTORS.forEach(sel => {
      try {
        document.querySelectorAll(sel).forEach(el => {
          if (!el.classList.contains('mt-hidden')) {
            el.style.display = 'none';
            el.classList.add('mt-hidden');
          }
        });
      } catch(e) {}
    });
  }

  function hideFeaturesForUser() {
    if (!mtUser) return;
    hideApplied = true;

    if (mtUser.is_admin) {
      console.log('[MT] Admin mode — all features visible');
      addBootMarker('MT admin ✓');
      return;
    }

    console.log('[MT] User mode — hiding features for', mtUser.username);
    applyHidden();
    addBootMarker('MT user ✓');
  }

  // ── User menu at the native sidebar account area ──
  // ComfyUI renders the bottom toolbar with .mt-auto; the account/logout icon
  // normally lives at the bottom. We mount our user button right there.
  function ensureUserMenuPresent() {
    if (menuMounted || !mtUser) return;

    // Locate the bottom toolbar of the sidebar
    const bottomToolbar = document.querySelector('.side-tool-bar-container [class*="mt-auto"], .side-tool-bar-container > div:last-child');
    if (!bottomToolbar) {
      addBootMarker('MT: toolbar missing, retry');
      return; // MutationObserver will retry
    }

    // Insert as the LAST item of bottom toolbar (native account position)
    const userBtn = createUserMenuButton();
    bottomToolbar.appendChild(userBtn);
    menuMounted = true;
    addBootMarker('MT: menu mounted ✓');
    console.log('[MT] User menu mounted at sidebar account area');
  }

  function createUserMenuButton() {
    const btn = document.createElement('button');
    btn.className = 'mt-user-btn comfy-menu-button-wrapper flex shrink-0 cursor-pointer flex-col items-center justify-center p-2 transition-colors';
    btn.style.cssText = 'color: var(--fg-color, #e0e0e0); background: none; border: none; position: relative;';
    btn.title = '用户菜单';
    const initial = (mtUser?.display_name || mtUser?.username || 'U').charAt(0).toUpperCase();
    btn.innerHTML = `
      <div class="side-bar-button-content flex flex-col items-center gap-2">
        <div class="sidebar-icon-wrapper relative">
          <div class="side-bar-button-icon icon-[lucide--user] mt-user-avatar" style="font-size:20px;line-height:1;">${initial}</div>
        </div>
        <div class="side-bar-button-label line-clamp-2 w-max max-w-[calc(var(--sidebar-width)-var(--sidebar-padding))] text-center text-2xs wrap-break-word whitespace-normal" style="max-width:60px;overflow:hidden;text-overflow:ellipsis;">
          ${mtUser?.display_name || mtUser?.username || '用户'}
        </div>
      </div>
    `;
    btn.onclick = function(e) {
      e.stopPropagation();
      showUserMenu(btn);
    };
    return btn;
  }

  function showUserMenu(anchor) {
    const existing = document.querySelector('.mt-user-menu');
    if (existing) { existing.remove(); return; }

    const menu = document.createElement('div');
    menu.className = 'mt-user-menu';
    menu.style.cssText = `
      position: fixed; left: 64px; bottom: 16px;
      background: var(--comfy-menu-bg, #1c1e24);
      border: 1px solid var(--border-color, rgba(255,255,255,0.12));
      border-radius: 10px; padding: 8px 0; min-width: 200px; z-index: 10002;
      box-shadow: 0 12px 32px rgba(0,0,0,0.5);
      color: var(--fg-color, #e0e0e0); font-size: 13px;
    `;
    const roleText = mtUser?.is_admin ? '管理员' : '普通用户';
    menu.innerHTML = `
      <div style="padding:8px 16px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">
        <div style="font-weight:600;font-size:14px;">${mtUser?.display_name || mtUser?.username || '用户'}</div>
        <div style="font-size:11px;color:var(--descrip-text,#888);margin-top:2px;">${roleText} · ${mtUser?.username || ''}</div>
      </div>
      ${mtUser?.is_admin ? '<button onclick="mtOpenAdmin()" class="mt-menu-item">⚙ 管理控制台</button>' : ''}
      <button onclick="mtLogout()" class="mt-menu-item" style="color:#ef4444;">退出登录</button>
    `;

    // Styles for menu items (idempotent)
    try {
      if (!document.getElementById('mt-menu-style')) {
        const style = document.createElement('style');
        style.id = 'mt-menu-style';
        style.textContent = `
          .mt-menu-item { width:100%; padding:9px 16px; text-align:left; background:none; border:none;
            color:var(--fg-color,#e0e0e0); font-size:13px; cursor:pointer; transition:background .15s; }
          .mt-menu-item:hover { background:var(--comfy-input-bg,#2a2d35); }
        `;
        document.head.appendChild(style);
      }
    } catch(e) {}

    document.body.appendChild(menu);

    setTimeout(() => {
      document.addEventListener('click', function closeMenu(e) {
        if (!menu.contains(e.target) && !e.target.closest('.mt-user-btn')) {
          menu.remove();
          document.removeEventListener('click', closeMenu);
        }
      });
    }, 0);
  }

  window.mtLogout = function() {
    try {
      // Save this account's workflow state (drafts + open tabs) to an
      // account-scoped key BEFORE clearing, so switching back to this account
      // later restores its own drafts/open workflows — instead of losing them.
      try {
        const uid = mtUser && mtUser.id;
        if (uid) {
          localStorage.setItem('mt_wf_state:' + uid, JSON.stringify(snapshotComfyWorkflowState()));
        }
      } catch(e) {}
      localStorage.removeItem('mt_token');
      localStorage.removeItem('mt_user');
      // Clear ComfyUI workflow/tab/draft state so the next login is clean.
      try { clearComfyWorkflowState(); } catch(e) {}
      // Clear auth cookie
      document.cookie = 'mt_token=; Path=/; Max-Age=0';
    } catch(e) {}
    window.location.href = '/';
  };

  // Capture all ComfyUI workflow pointers (drafts + open tabs + active tab)
  // from localStorage/sessionStorage so they can be restored per-account.
  function snapshotComfyWorkflowState() {
    const P = 'Comfy.Workflow.';
    const local = {};
    const session = {};
    function collect(store, target) {
      if (!store) return;
      try {
        const keys = [];
        for (let i = 0; i < store.length; i++) keys.push(store.key(i));
        for (const k of keys) {
          if (k && k.indexOf(P) === 0) target[k] = store.getItem(k);
        }
      } catch(e) {}
    }
    collect(window.localStorage, local);
    collect(window.sessionStorage, session);
    return { local: local, session: session };
  }

  // Restore a previously snapshotted workflow state into storage.
  function restoreComfyWorkflowState(snap) {
    if (!snap) return;
    try { clearComfyWorkflowState(); } catch(e) {}
    function write(store, obj) {
      if (!store) return;
      for (const k of Object.keys(obj || {})) {
        try { store.setItem(k, obj[k]); } catch(e) {}
      }
    }
    write(window.localStorage, snap.local);
    write(window.sessionStorage, snap.session);
  }

  // Remove ComfyUI's per-tab/cross-session workflow pointers (not scoped by
  // account) — prevents the previous user's open workflows from lingering.
  function clearComfyWorkflowState() {
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

  window.mtOpenAdmin = function() {
    openAdminPanel();
  };

  // ── Admin Management Panel (3 tabs: Users / Z&A Workflows / All Workflows) ──
  let adminTab = 'users';
  let adminData = null;

  async function openAdminPanel(tab) {
    if (tab) adminTab = tab;
    document.querySelector('.mt-admin-panel')?.remove();
    await loadAdminData();
    renderAdminPanel();
  }

  async function loadAdminData() {
    try {
      const [usersR, wfR] = await Promise.all([
        fetch(MT_API + '/admin/users', { headers: getAuthHeaders() }),
        fetch(MT_API + '/admin/workflows', { headers: getAuthHeaders() })
      ]);
      if (!usersR.ok || !wfR.ok) {
        alert('无管理员权限');
        adminData = null;
        return;
      }
      adminData = {
        users: (await usersR.json()).items || [],
        workflows: (await wfR.json()).items || []
      };
    } catch(e) {
      alert('加载管理数据失败');
      adminData = null;
    }
  }

  function renderAdminPanel() {
    if (!adminData) return;
    const { users, workflows } = adminData;
    const zaWorkflows = workflows.filter(w => w.is_za);
    const userWorkflows = workflows.filter(w => !w.is_za);

    const panel = document.createElement('div');
    panel.className = 'mt-admin-panel';
    panel.style.cssText = `
      position: fixed; inset: 0; z-index: 10001;
      background: rgba(0,0,0,0.55);
      display: flex; align-items: center; justify-content: center;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
    `;
    panel.innerHTML = `
      <div style="background:var(--comfy-menu-bg,#1c1e24);border:1px solid var(--border-color,rgba(255,255,255,0.12));border-radius:14px;width:760px;max-width:94vw;max-height:86vh;display:flex;flex-direction:column;color:var(--fg-color,#e0e0e0);box-shadow:0 24px 80px rgba(0,0,0,0.5);">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">
          <h2 style="font-size:17px;font-weight:600;margin:0;">管理控制台</h2>
          <button onclick="document.querySelector('.mt-admin-panel').remove()" style="background:none;border:none;color:var(--descrip-text,#888);font-size:20px;cursor:pointer;line-height:1;">✕</button>
        </div>
        <div style="display:flex;gap:4px;padding:10px 20px 0;">
          <button onclick="mtAdminTab('users')" style="padding:7px 16px;border:none;border-radius:8px 8px 0 0;font-size:13px;cursor:pointer;${adminTab==='users' ? 'background:var(--comfy-input-bg,#2a2d35);color:var(--fg-color,#e0e0e0);font-weight:600;' : 'background:none;color:var(--descrip-text,#888);'}">用户管理 (${users.length})</button>
          <button onclick="mtAdminTab('za')" style="padding:7px 16px;border:none;border-radius:8px 8px 0 0;font-size:13px;cursor:pointer;${adminTab==='za' ? 'background:var(--comfy-input-bg,#2a2d35);color:var(--fg-color,#e0e0e0);font-weight:600;' : 'background:none;color:var(--descrip-text,#888);'}">Z&A 共享 (${zaWorkflows.length})</button>
          <button onclick="mtAdminTab('all')" style="padding:7px 16px;border:none;border-radius:8px 8px 0 0;font-size:13px;cursor:pointer;${adminTab==='all' ? 'background:var(--comfy-input-bg,#2a2d35);color:var(--fg-color,#e0e0e0);font-weight:600;' : 'background:none;color:var(--descrip-text,#888);'}">全部工作流 (${workflows.length})</button>
        </div>
        <div style="flex:1;overflow:auto;padding:16px 20px 20px;border-top:1px solid var(--border-color,rgba(255,255,255,0.08));">
          ${adminTab === 'users' ? renderUsersTab(users) : (adminTab === 'za' ? renderZaTab(zaWorkflows) : renderAllTab(workflows))}
        </div>
      </div>
    `;
    document.body.appendChild(panel);
  }

  function renderUsersTab(users) {
    return `
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="color:var(--descrip-text,#888);text-align:left;">
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">用户名</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">显示名</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">角色</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">状态</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">操作</th>
        </tr></thead>
        <tbody>
          ${users.map(u => `
            <tr>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${u.username}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${u.display_name || '-'}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">
                ${u.username === '15096756699' ? '<span style="color:#4f6ef7;font-weight:500;">主管理员</span>' : `<button onclick="mtSetRole(${u.id}, ${!u.is_admin})" style="padding:2px 8px;border-radius:4px;font-size:12px;cursor:pointer;border:1px solid var(--border-color,rgba(255,255,255,0.15));background:none;color:${u.is_admin ? '#4f6ef7' : 'var(--descrip-text,#888)'};">${u.is_admin ? '管理员' : '设为管理员'}</button>`}
              </td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${u.is_active ? '<span style="color:#34c759;">已激活</span>' : '<span style="color:#ff3b30;">已禁用</span>'}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">
                ${u.username !== '15096756699' ? `<button onclick="mtToggleUser(${u.id})" style="padding:3px 10px;background:${u.is_active ? '#ff3b30' : '#34c759'};border:none;border-radius:4px;color:#fff;font-size:12px;cursor:pointer;">${u.is_active ? '禁用' : '启用'}</button>` : '<span style="color:#888;font-size:11px;">—</span>'}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  function renderZaTab(zaWorkflows) {
    return `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div style="font-size:13px;color:var(--descrip-text,#888);">Z&A 工作流为全员共享，由管理员维护</div>
        <button onclick="mtUploadZa()" style="padding:6px 14px;background:#4f6ef7;border:none;border-radius:6px;color:#fff;font-size:13px;cursor:pointer;">+ 上传共享工作流</button>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="color:var(--descrip-text,#888);text-align:left;">
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">名称</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">说明</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">更新</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">操作</th>
        </tr></thead>
        <tbody>
          ${zaWorkflows.length === 0 ? '<tr><td colspan="4" style="padding:20px;text-align:center;color:#888;font-size:13px;">暂无共享工作流</td></tr>' : zaWorkflows.map(w => `
            <tr>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));"><span style="color:#4f6ef7;font-size:11px;padding:1px 6px;border-radius:3px;background:rgba(79,110,247,0.15);margin-right:6px;">Z&A</span>${w.display_name || w.name}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));color:var(--descrip-text,#888);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${w.description || '-'}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));color:var(--descrip-text,#888);font-size:12px;">${(w.updated_at || w.created_at || '').slice(0,10)}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">
                <button onclick="mtDeleteWf(${w.id})" style="padding:3px 10px;background:none;border:1px solid rgba(255,59,48,0.4);border-radius:4px;color:#ff3b30;font-size:12px;cursor:pointer;">删除</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  function renderAllTab(workflows) {
    return `
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="color:var(--descrip-text,#888);text-align:left;">
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">名称</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">类型</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">归属</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">更新</th>
          <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">操作</th>
        </tr></thead>
        <tbody>
          ${workflows.length === 0 ? '<tr><td colspan="5" style="padding:20px;text-align:center;color:#888;font-size:13px;">暂无工作流</td></tr>' : workflows.map(w => `
            <tr>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${w.display_name || w.name}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${w.is_za ? '<span style="color:#4f6ef7;font-size:11px;padding:1px 6px;border-radius:3px;background:rgba(79,110,247,0.15);">Z&A</span>' : '<span style="color:#9ca3af;font-size:11px;padding:1px 6px;border-radius:3px;background:rgba(156,163,175,0.15);">自定义</span>'}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${w.owner_username || '<span style="color:#4f6ef7;">全员共享</span>'}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));color:var(--descrip-text,#888);font-size:12px;">${(w.updated_at || w.created_at || '').slice(0,10)}</td>
              <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">
                <button onclick="mtDeleteWf(${w.id})" style="padding:3px 10px;background:none;border:1px solid rgba(255,59,48,0.4);border-radius:4px;color:#ff3b30;font-size:12px;cursor:pointer;">删除</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  window.mtAdminTab = function(tab) {
    adminTab = tab;
    document.querySelector('.mt-admin-panel')?.remove();
    renderAdminPanel();
  };

  window.mtToggleUser = async function(userId) {
    try {
      const r = await fetch(MT_API + `/admin/users/${userId}/toggle-active`, {
        method: 'POST', headers: getAuthHeaders()
      });
      if (r.ok) {
        await loadAdminData();
        document.querySelector('.mt-admin-panel')?.remove();
        renderAdminPanel();
      } else {
        const d = await r.json();
        alert(d.detail || '操作失败');
      }
    } catch(e) { alert('网络错误'); }
  };

  window.mtSetRole = async function(userId, makeAdmin) {
    if (!confirm(makeAdmin ? '确定将该用户设为管理员？' : '确定取消该用户的管理员权限？')) return;
    try {
      const r = await fetch(MT_API + `/admin/users/${userId}/role`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ is_admin: makeAdmin })
      });
      if (r.ok) {
        await loadAdminData();
        document.querySelector('.mt-admin-panel')?.remove();
        renderAdminPanel();
      } else {
        const d = await r.json();
        alert(d.detail || '操作失败');
      }
    } catch(e) { alert('网络错误'); }
  };

  window.mtDeleteWf = async function(workflowId) {
    if (!confirm('确定删除该工作流？')) return;
    try {
      const r = await fetch(MT_API + `/workflows/${workflowId}`, {
        method: 'DELETE', headers: getAuthHeaders()
      });
      if (r.ok) {
        await loadAdminData();
        document.querySelector('.mt-admin-panel')?.remove();
        renderAdminPanel();
      } else {
        const d = await r.json();
        alert(d.detail || '删除失败');
      }
    } catch(e) { alert('网络错误'); }
  };

  window.mtUploadZa = function() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        const name = file.name.replace(/\.json$/i, '');
        const r = await fetch(MT_API + '/workflows', {
          method: 'POST', headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, display_name: name, is_za: true, workflow_data: data })
        });
        if (r.ok) {
          await loadAdminData();
          document.querySelector('.mt-admin-panel')?.remove();
          renderAdminPanel();
        } else {
          const d = await r.json();
          alert(d.detail || '上传失败');
        }
      } catch(e) { alert('文件解析失败'); }
    };
    input.click();
  };

  // ── Workflow Type Badges ──
  // NOTE: disabled — selector was too broad and mislabeled elements.
  // Real workflow-type distinction is enforced server-side (Z&A shared vs
  // per-user custom). A precise frontend badge can be added later once the
  // exact workflow-list DOM structure is confirmed.
  function setupWorkflowBadges() {
    // Intentionally no-op for now
  }

  // ── Preview Image Persistence ──
  function setupPreviewPersistence() {
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
      const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
      const method = (args[1]?.method || 'GET').toUpperCase();
      if (method === 'DELETE' && (url.includes('/workflows/') || url.includes('/api/workflows/'))) {
        const match = url.match(/workflows\/([^/?#]+)/);
        if (match) {
          const wfId = decodeURIComponent(match[1]);
          try {
            fetch(MT_API + '/previews/' + encodeURIComponent(wfId), {
              method: 'DELETE',
              headers: getAuthHeaders()
            }).catch(() => {});
          } catch(e) {}
        }
      }
      return originalFetch.apply(this, args);
    };
    console.log('[MT] Preview persistence ready');
  }

  // ── Preview Image Restore (refresh survival) ──
  // Restore persisted previews into nodeOutputs so the native image URL
  // builder (/view?type=output) can serve them after refresh/restart.
  // Returns true when the graph had PreviewImage nodes to restore into.
  async function restorePreviewImages() {
    try {
      if (!mtUser) { setDiag('restore: no user'); return false; }
      const app = window.app;
      setDiag('restore: window.app=' + (app ? 'YES' : 'NO'));
      const graph = app?.graph || app?.rootGraph;
      if (!graph) { setDiag('restore: no graph (app=' + (app ? 'yes' : 'no') + ')'); return false; }
      const previewNodes = graph._nodes.filter(n => (n.type || '').includes('PreviewImage'));
      setDiag('restore: nodes=' + previewNodes.length);
      if (!previewNodes.length) return false;

      const r = await fetch(MT_API + '/previews/all', { headers: getAuthHeaders() });
      if (!r.ok) { setDiag('restore: api ' + r.status); return false; }
      const data = await r.json();
      const previews = data.items || [];
      if (!previews.length) { setDiag('restore: 0 previews'); return false; }

      // Current workflow id
      let wfId = null;
      try {
        wfId = app?.rootGraph?.id ||
               app?.graph?.id ||
               (app?.graph?.serialize ? app.graph.serialize().id : null) ||
               app?.workflowManager?.activeWorkflow?.id ||
               null;
      } catch(e) {}

      let wfPreviews = wfId ? previews.filter(p => p.workflow_id === wfId) : [];
      // Fallback: match by node_id across this user's previews
      if (!wfPreviews.length) {
        const nodeIds = new Set(previewNodes.map(n => String(n.id)));
        wfPreviews = previews.filter(p => nodeIds.has(String(p.node_id)));
      }

      // The PreviewImage node renders via LGraphNode.vue's `nodeMedia`
      // computed, which reads `nodeOutputs.nodeOutputs[locatorId]` (the
      // nodeOutputs store ref) and requires output.images to be non-empty.
      // The correct way to populate that store ref from an extension is to
      // dispatch the native `executed` event — app.ts listens and calls
      // setNodeOutputsByExecutionId() which writes the nodeOutputs store ref.
      const api = (typeof window !== 'undefined' && window.comfyAPI && window.comfyAPI.api && window.comfyAPI.api.api)
                  || window.app?.api;
      setDiag('restore: api=' + (window.comfyAPI && window.comfyAPI.api && window.comfyAPI.api.api ? 'comfyAPI' : (window.app?.api ? 'app.api' : 'NONE')));

      let injected = 0;
      const cacheMap = {};
      for (const node of previewNodes) {
        const locatorId = String(node.id);
        const p = wfPreviews.find(x => String(x.node_id) === locatorId);
        if (!p) continue; // no persisted preview for THIS node — leave empty
        const sub = 'mt_previews/' + mtUser.id + '/' + p.workflow_id;
        const url = '/view?filename=' + encodeURIComponent(p.filename) +
                    '&subfolder=' + encodeURIComponent(sub) +
                    '&type=output';

        // (1) Dispatch the native 'executed' event so the Pinia store
        // nodeOutputs ref is populated — this is the same path live preview
        // uses (app.ts -> setNodeOutputsByExecutionId -> store), and it's
        // what updatePreviews reads to re-render the node on next redraw.
        try {
          api.dispatchCustomEvent('executed', {
            node: locatorId,
            display_node: locatorId,
            output: { images: [{ filename: p.filename, subfolder: sub, type: 'output' }] },
            prompt_id: 'mt-restore-' + Date.now(),
            merge: false
          });
        } catch(e) {}

        // (2) Directly set node.imgs as a belt-and-suspenders fallback, so
        // even if the store->render path is delayed, the canvas shows it.
        try {
          const img = new Image();
          img.onload = function() {
            try {
              node.previewMediaType = 'image';
              node.imageIndex = null;
              node.imgs = [img];
              if (node.graph && node.graph.setDirtyCanvas) node.graph.setDirtyCanvas(true, true);
              if (graph && graph.setDirtyCanvas) graph.setDirtyCanvas(true, true);
            } catch(e) {}
          };
          img.src = url;
        } catch(e) {
          console.error('[MT] set node.imgs failed', locatorId, e);
        }

        cacheMap[locatorId] = url;
        injected++;
      }
      if (injected) {
        // Force a canvas redraw so updatePreviews picks up the store data.
        try {
          if (graph && graph.setDirtyCanvas) graph.setDirtyCanvas(true, true);
        } catch(e) {}
        setDiag('restore: OK injected=' + injected + ' (executed+imgs)');
      }
      return injected > 0;
    } catch(e) {
      console.error('[MT] restorePreviewImages error:', e);
      setDiag('restore: error');
      return false;
    }
  }

  // Poll restore until the graph is ready (ComfyUI SPA mounts async).
  function startRestorePolling() {
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts++;
      const ok = await restorePreviewImages();
      if (ok || attempts > 15) { // ~30s cap
        clearInterval(timer);
        if (ok) document.title = '[MT] restore polling: done';
      }
    }, 2000);
  }

  // ── Initialization ──
  async function init() {
    document.title = '[MT] init: start';
    setDiag('init: start');
    // Skip if on login page
    if (document.querySelector('.login-card')) { setDiag('init: login page'); return; }

    // Fetch user
    setDiag('init: fetching user...');
    await fetchUser();
    setDiag(mtUser ? ('init: user=' + mtUser.username) : 'init: NO USER');
    if (!mtUser) {
      // Not logged in — middleware serves login page; force reload if somehow here
      if (!document.querySelector('.login-card')) {
        addBootMarker('MT: no auth, reload');
        setDiag('init: no auth, reload');
        window.location.reload();
      }
      return;
    }

    // Restore persisted previews FIRST — poll until the graph is ready.
    // Do this before any other UI work so a failure elsewhere can't block it.
    setDiag('init: starting restore...');
    try { startRestorePolling(); setDiag('init: restore polling started'); }
    catch(e) { setDiag('init: restore start ERR ' + (e && e.message || e)); }

    // Apply overrides (each isolated so one failure can't stop the rest)
    try { hideFeaturesForUser(); setDiag('init: hide ok'); } catch(e) { setDiag('init: hide ERR'); }
    try { ensureUserMenuPresent(); } catch(e) {}
    try { setupWorkflowBadges(); } catch(e) {}
    try { setupPreviewPersistence(); } catch(e) {}

    // Re-restore previews whenever a workflow is loaded/switched.
    // ComfyUI's loadGraphData lives on window.comfyAPI.app.app (the real
    // ComfyApp instance), NOT on window.app. Hook BOTH to be safe, and
    // restore with a longer delay since the graph is rebuilt async.
    try {
      const candidates = [];
      if (window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app) candidates.push(window.comfyAPI.app.app);
      if (window.app && window.app !== window.comfyAPI?.app?.app) candidates.push(window.app);
      let hooked = false;
      for (const app of candidates) {
        if (app && typeof app.loadGraphData === 'function') {
          const origLoad = app.loadGraphData.bind(app);
          app.loadGraphData = function(...args) {
            const ret = origLoad(...args);
            setTimeout(restorePreviewImages, 1200);
            setTimeout(restorePreviewImages, 3000);
            return ret;
          };
          hooked = true;
        }
      }
      console.log('[MT] loadGraphData hook ' + (hooked ? 'OK' : 'FAILED — no loadGraphData found'));
    } catch(e) {
      console.error('[MT] loadGraphData hook error:', e);
    }

    // After each execution finishes, restore persisted previews — the native
    // frontend revokes previews on execution complete (blob lifecycle), so we
    // re-inject persisted ones so they stay visible without F5.
    try {
      const app = window.app;
      if (app && app.api && app.api.addEventListener) {
        app.api.addEventListener('execution_success', () => {
          setTimeout(restorePreviewImages, 300);
        });
        app.api.addEventListener('executed', (evt) => {
          try {
            const d = evt?.detail || {};
            document.title = '[MT-diag] executed node=' + (d.node ?? d.display_node) + ' out=' + JSON.stringify(d.output || {}).slice(0, 100);
          } catch(e) {}
        });
        console.log('[MT] executed/execution_success listeners registered');
      }
    } catch(e) {
      console.error('[MT] diag error:', e);
    }

    // Watch for Vue re-renders: re-hide + re-mount menu
    const observer = new MutationObserver(() => {
      if (mtUser && !mtUser.is_admin) applyHidden();
      if (mtUser) ensureUserMenuPresent();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    console.log('[MT] Initialized for:', mtUser.username, mtUser.is_admin ? '(admin)' : '(user)');
  }

  // Start only after DOM exists
  function start() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', start);
      return;
    }
    addBootMarker('MT loading...');
    init().catch(e => {
      console.error('[MT] init error:', e);
      addBootMarker('MT error: ' + (e && e.message ? e.message : e));
    });
  }

  start();
})();
