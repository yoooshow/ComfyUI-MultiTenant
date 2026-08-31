// ComfyUI Multi-Tenant Frontend Extension v3
// Auto-loaded by ComfyUI from web/ directory.
// Strategy: never touch DOM at module top-level (ComfyUI dynamic-imports
// extensions before Vue mounts). All DOM work happens after init() on
// DOMContentLoaded + MutationObserver retry. User menu mounts at the
// bottom of the native sidebar account area (does NOT replace Settings).

(function() {
  'use strict';

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

  // ── Auth Helpers ──
  function getToken() {
    if (mtToken) return mtToken;
    try { mtToken = localStorage.getItem('mt_token') || ''; } catch(e) { mtToken = ''; }
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
      localStorage.removeItem('mt_token');
      localStorage.removeItem('mt_user');
      // Clear auth cookie
      document.cookie = 'mt_token=; Path=/; Max-Age=0';
    } catch(e) {}
    window.location.href = '/';
  };

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
  // ComfyUI shows PreviewImage output from app.nodePreviewImages[locatorId].
  // After refresh/restart, temp files are gone but our persisted previews
  // survive. On workflow load, we fetch persisted previews and re-inject
  // their URLs into app.nodePreviewImages so nodes display them again.
  async function restorePreviewImages() {
    try {
      if (!mtUser) return;
      // Fetch all persisted previews for this user (grouped by workflow)
      const r = await fetch(MT_API + '/previews/all', { headers: getAuthHeaders() });
      if (!r.ok) return;
      const data = await r.json();
      const previews = data.items || [];
      if (!previews.length) return;

      // Get current workflow id from ComfyUI graph state
      const app = window.app;
      let wfId = null;
      try {
        wfId = app?.rootGraph?.id ||
               app?.graph?.id ||
               (app?.graph?.serialize ? app.graph.serialize().id : null) ||
               app?.workflowManager?.activeWorkflow?.id ||
               null;
      } catch(e) {}

      // Match previews to this workflow
      const wfPreviews = previews.filter(p => p.workflow_id === wfId);
      if (!wfPreviews.length) return;

      // Find PreviewImage nodes in current graph
      const graph = app?.graph || app?.rootGraph;
      if (!graph) return;
      const previewNodes = graph._nodes.filter(n => (n.type || '').includes('PreviewImage'));
      if (!previewNodes.length) return;

      // Build preview URL for each node. ONLY exact node_id match — a
      // PreviewImage node that never ran must NOT get another node's image.
      if (!app.nodePreviewImages) app.nodePreviewImages = {};
      previewNodes.forEach((node) => {
        const locatorId = String(node.id);
        const p = wfPreviews.find(x => String(x.node_id) === locatorId);
        if (!p) return; // no persisted preview for THIS node — leave empty
        const url = MT_API + '/previews/' + encodeURIComponent(p.workflow_id) + '/img/' + encodeURIComponent(p.filename);
        app.nodePreviewImages[locatorId] = [url];
        console.log('[MT] Restored preview for node', locatorId, '->', url);
      });

      // Refresh node display
      try {
        if (app.canvas) app.canvas.draw(true, true);
      } catch(e) {}
    } catch(e) {
      console.error('[MT] restorePreviewImages error:', e);
    }
  }

  // ── Initialization ──
  async function init() {
    // Skip if on login page
    if (document.querySelector('.login-card')) return;

    // Fetch user
    await fetchUser();
    if (!mtUser) {
      // Not logged in — middleware serves login page; force reload if somehow here
      if (!document.querySelector('.login-card')) {
        addBootMarker('MT: no auth, reload');
        window.location.reload();
      }
      return;
    }

    // Apply overrides
    hideFeaturesForUser();
    ensureUserMenuPresent();
    setupWorkflowBadges();
    setupPreviewPersistence();
    // Restore persisted previews after ComfyUI app is ready
    setTimeout(restorePreviewImages, 2500);

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
