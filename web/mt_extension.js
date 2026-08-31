// ComfyUI Multi-Tenant Frontend Extension v2
// Auto-loaded by ComfyUI from web/ directory
// Handles: role-based UI hiding, user menu (replaces Settings), workflow badges, preview persistence

(function() {
  'use strict';

  const MT_API = '/api/mt';
  let mtUser = null;
  let mtToken = localStorage.getItem('mt_token');
  let hideApplied = false;

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
        // Token expired or invalid — redirect to login
        localStorage.removeItem('mt_token');
        localStorage.removeItem('mt_user');
        mtToken = null;
        window.location.reload();
      }
    } catch(e) { console.error('[MT] fetchUser error:', e); }
    return null;
  }

  // ── UI Overrides ──
  // Confirmed selectors from ComfyUI frontend 1.51.9 source:
  //   model-library -> [data-testid="model-library-tab-button"]
  //   templates     -> .templates-tab-button
  //   console       -> SidebarBottomPanelToggleButton (icon ph--terminal-bold)
  //   settings      -> SidebarSettingsButton (icon lucide--settings) — replaced with user menu
  //   shortcuts     -> SidebarShortcutsToggleButton (icon lucide--keyboard)
  //   ComfyUI Manager -> (installed separately, hidden via .comfyui-manager-button or [data-testid])

  const HIDDEN_SELECTORS = [
    // Model library (模型库)
    '[data-testid="model-library-tab-button"]',
    // Templates (模板)
    '.templates-tab-button',
    // Console / bottom panel toggle (控制台)
    '.side-bar-button-icon.icon-\\[ph--terminal-bold\\]',
    // Shortcuts panel (快捷键 — kept for admins, hidden for users)
    '.side-bar-button-icon.icon-\\[lucide--keyboard\\]',
    // ComfyUI Manager button (右上角 管理扩展功能)
    '.comfyui-manager-button',
    '[data-testid="manager-button"]',
    '.manager-button',
    '#comfyui-manager-button',
  ];

  const USER_VISIBLE_SELECTORS = [
    // Node library (节点库) — users need this to build workflows
    '[data-testid="node-library-tab-button"]',
    // Workflows (工作流) — users need this
    '[data-testid="workflows-tab-button"]',
  ];

  function hideFeaturesForUser() {
    if (!mtUser) return;
    if (hideApplied) return;
    hideApplied = true;

    if (mtUser.is_admin) {
      console.log('[MT] Admin mode — all features visible');
      return;
    }

    console.log('[MT] User mode — hiding features for', mtUser.username);

    // Hide specified buttons
    HIDDEN_SELECTORS.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = 'none';
        el.classList.add('mt-hidden');
      });
    });

    // Replace settings button with user menu
    replaceSettingsWithUserMenu();

    // Watch for dynamic re-renders (Vue may re-create DOM)
    const observer = new MutationObserver(() => {
      HIDDEN_SELECTORS.forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
          if (!el.classList.contains('mt-hidden')) {
            el.style.display = 'none';
            el.classList.add('mt-hidden');
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function replaceSettingsWithUserMenu() {
    // Find the settings button (SidebarIcon with lucide--settings icon in bottom toolbar)
    const settingsBtn = document.querySelector('.side-bar-button-icon.icon-\\[lucide--settings\\]')?.closest('button, .comfy-menu-button-wrapper, div');
    const bottomToolbar = document.querySelector('.side-tool-bar-container [class*="mt-auto"], .side-tool-bar-container > div:last-child');

    if (!settingsBtn) {
      console.log('[MT] Settings button not found, adding user menu to bottom toolbar');
      if (bottomToolbar) {
        bottomToolbar.appendChild(createUserMenuButton());
      }
      return;
    }

    // Replace settings with user menu button
    const userBtn = createUserMenuButton();
    if (settingsBtn.parentNode) {
      settingsBtn.parentNode.replaceChild(userBtn, settingsBtn);
    }
  }

  function createUserMenuButton() {
    const btn = document.createElement('button');
    btn.className = 'mt-user-btn comfy-menu-button-wrapper flex shrink-0 cursor-pointer flex-col items-center justify-center p-2 transition-colors';
    btn.style.cssText = 'color: var(--fg-color, #e0e0e0); background: none; border: none;';
    btn.innerHTML = `
      <div class="side-bar-button-content flex flex-col items-center gap-2">
        <div class="sidebar-icon-wrapper relative">
          <div class="side-bar-button-icon icon-[lucide--user] mt-user-avatar" style="font-size:20px;line-height:1;">
            ${mtUser?.display_name ? mtUser.display_name.charAt(0).toUpperCase() : 'U'}
          </div>
        </div>
        <div class="side-bar-button-label line-clamp-2 w-max max-w-[calc(var(--sidebar-width)-var(--sidebar-padding))] text-center text-2xs wrap-break-word whitespace-normal">
          ${mtUser?.display_name || mtUser?.username || '用户'}
        </div>
      </div>
    `;
    btn.onclick = showUserMenu;
    return btn;
  }

  function showUserMenu() {
    const existing = document.querySelector('.mt-user-menu');
    if (existing) { existing.remove(); return; }

    const menu = document.createElement('div');
    menu.className = 'mt-user-menu';
    menu.style.cssText = `
      position: fixed;
      bottom: 60px;
      left: 60px;
      background: var(--comfy-menu-bg, #1c1e24);
      border: 1px solid var(--border-color, rgba(255,255,255,0.1));
      border-radius: 8px;
      padding: 8px 0;
      min-width: 200px;
      z-index: 10000;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
      color: var(--fg-color, #e0e0e0);
    `;
    const roleText = mtUser?.is_admin ? '管理员' : '普通用户';
    menu.innerHTML = `
      <div style="padding:8px 16px;font-size:13px;color:var(--descrip-text, #888);border-bottom:1px solid var(--border-color, rgba(255,255,255,0.08));">
        <div style="color:var(--fg-color, #e0e0e0);font-weight:500;font-size:14px;">${mtUser?.display_name || mtUser?.username || '用户'}</div>
        <div style="font-size:11px;margin-top:2px;">${roleText}</div>
      </div>
      ${mtUser?.is_admin ? '<button onclick="mtOpenAdmin()" class="mt-menu-item">管理控制台</button>' : ''}
      <button onclick="mtLogout()" class="mt-menu-item" style="color:#ef4444;">退出登录</button>
    `;

    // Add styles for menu items
    const style = document.createElement('style');
    style.textContent = `
      .mt-menu-item {
        width: 100%;
        padding: 8px 16px;
        text-align: left;
        background: none;
        border: none;
        color: var(--fg-color, #e0e0e0);
        font-size: 13px;
        cursor: pointer;
        transition: background 0.15s;
      }
      .mt-menu-item:hover { background: var(--comfy-input-bg, #2a2d35); }
    `;
    document.head.appendChild(style);

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

  window.mtOpenAdmin = function() {
    // Open admin panel (simple user management) — opens in modal
    fetchAdminUsers();
  };

  window.mtLogout = function() {
    localStorage.removeItem('mt_token');
    localStorage.removeItem('mt_user');
    window.location.reload();
  };

  // ── Admin User Management Panel ──
  async function fetchAdminUsers() {
    try {
      const r = await fetch(MT_API + '/admin/users', { headers: getAuthHeaders() });
      if (!r.ok) {
        alert('无管理员权限');
        return;
      }
      const data = await r.json();
      showAdminPanel(data.items || []);
    } catch(e) {
      alert('加载用户列表失败');
    }
  }

  function showAdminPanel(users) {
    // Close existing
    document.querySelector('.mt-admin-panel')?.remove();

    const panel = document.createElement('div');
    panel.className = 'mt-admin-panel';
    panel.style.cssText = `
      position: fixed;
      inset: 0;
      z-index: 10001;
      background: rgba(0,0,0,0.5);
      display: flex;
      align-items: center;
      justify-content: center;
    `;
    panel.innerHTML = `
      <div style="background:var(--comfy-menu-bg,#1c1e24);border:1px solid var(--border-color,rgba(255,255,255,0.1));border-radius:12px;padding:24px;width:600px;max-width:90vw;max-height:80vh;overflow:auto;color:var(--fg-color,#e0e0e0);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h2 style="font-size:18px;font-weight:600;margin:0;">用户管理</h2>
          <button onclick="document.querySelector('.mt-admin-panel').remove()" style="background:none;border:none;color:var(--descrip-text,#888);font-size:20px;cursor:pointer;">✕</button>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="color:var(--descrip-text,#888);text-align:left;">
              <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">用户名</th>
              <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">显示名</th>
              <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">角色</th>
              <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">状态</th>
              <th style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.08));">操作</th>
            </tr>
          </thead>
          <tbody>
            ${users.map(u => `
              <tr>
                <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${u.username}</td>
                <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${u.display_name || '-'}</td>
                <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${u.is_admin ? '管理员' : '用户'}</td>
                <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">${u.is_active ? '✅ 激活' : '⛔ 禁用'}</td>
                <td style="padding:8px;border-bottom:1px solid var(--border-color,rgba(255,255,255,0.05));">
                  ${u.username !== '15096756699' ? `<button onclick="mtToggleUser(${u.id})" style="padding:3px 10px;background:${u.is_active ? '#ef4444' : '#10b981'};border:none;border-radius:4px;color:#fff;font-size:12px;cursor:pointer;">${u.is_active ? '禁用' : '启用'}</button>` : '<span style="color:#888;font-size:11px;">主管理员</span>'}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    document.body.appendChild(panel);
  }

  window.mtToggleUser = async function(userId) {
    try {
      const r = await fetch(MT_API + `/admin/users/${userId}/toggle-active`, {
        method: 'POST',
        headers: getAuthHeaders()
      });
      if (r.ok) {
        // Refresh panel
        document.querySelector('.mt-admin-panel')?.remove();
        fetchAdminUsers();
      } else {
        const d = await r.json();
        alert(d.detail || '操作失败');
      }
    } catch(e) {
      alert('网络错误');
    }
  };

  // ── Workflow Type Badges ──
  // Z&A workflows (admin-managed, shared) vs Custom workflows (per-user)
  function setupWorkflowBadges() {
    // Fetch workflow list from our API and tag sidebar workflow entries
    async function tagWorkflows() {
      try {
        const r = await fetch(MT_API + '/workflows', { headers: getAuthHeaders() });
        if (!r.ok) return;
        const data = await r.json();
        const zaNames = new Set(
          (data.items || []).filter(w => w.is_za).map(w => w.display_name || w.name)
        );

        // Find workflow sidebar items and add badges
        document.querySelectorAll('[data-testid="workflows-tab-button"]').forEach(() => {
          // Workflow items are in the sidebar tab content
          setTimeout(() => {
            document.querySelectorAll('.workflows-sidebar-item, [class*="workflow-item"], [class*="workflow-name"]').forEach(el => {
              if (el.querySelector('.mt-wf-badge')) return;
              const name = el.textContent.trim();
              if (!name || name.length > 40) return;
              const isZa = zaNames.has(name);
              const badge = document.createElement('span');
              badge.className = 'mt-wf-badge ' + (isZa ? 'za' : 'custom');
              badge.textContent = isZa ? 'Z&A' : '自定义';
              el.appendChild(badge);
            });
          }, 500);
        });
      } catch(e) {
        console.error('[MT] Failed to fetch workflows:', e);
      }
    }

    // Run on load and periodically (Vue re-renders)
    setTimeout(tagWorkflows, 1000);
    setInterval(tagWorkflows, 5000);
  }

  // ── Preview Image Persistence ──
  // PreviewImage node outputs persist across restart/refresh.
  // Backend stores references in DB; cleanup happens when workflow tab is closed.
  function setupPreviewPersistence() {
    // When workflow closes, tell backend to clean up its previews.
    // ComfyUI's app dispatches events on workflow open/close — hook into those.
    const api = window.api;
    if (!api) return;

    // Wrap fetch to detect workflow deletion
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
      const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
      const method = (args[1]?.method || 'GET').toUpperCase();

      // Detect workflow deletion (DELETE /workflows/... or /api/workflows/...)
      if (method === 'DELETE' && (url.includes('/workflows/') || url.includes('/api/workflows/'))) {
        // Extract workflow id/name from URL
        const match = url.match(/workflows\/([^/?#]+)/);
        if (match) {
          const wfId = decodeURIComponent(match[1]);
          // Notify backend to cleanup previews (fire and forget)
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
    console.log('[MT] Preview persistence ready (workflow close cleanup hooked)');
  }

  // ── Initialization ──
  async function init() {
    // Skip if on login page
    if (document.querySelector('.login-card')) return;

    // Fetch user
    await fetchUser();
    if (!mtUser) {
      // Not logged in — middleware serves login page on refresh; if we got here, force reload
      if (!document.querySelector('.login-card')) {
        window.location.reload();
      }
      return;
    }

    // Apply overrides
    hideFeaturesForUser();
    setupWorkflowBadges();
    setupPreviewPersistence();

    console.log('[MT] Initialized for:', mtUser.username, mtUser.is_admin ? '(admin)' : '(user)');
  }

  // Start when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
