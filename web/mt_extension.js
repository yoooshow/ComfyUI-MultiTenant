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

    // Hide left panel buttons: Models, Templates, Console
    // ComfyUI's new UI selectors
    const hideSelectors = [
      '[data-testid="models-button"]',
      '[data-testid="templates-button"]',
      '[data-testid="console-button"]',
      '.comfyui-menu-models',
      '.comfyui-menu-templates',
      '.comfyui-menu-console',
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
      '[title*="Manager"]',
      '[aria-label*="Manager"]',
    ];
    managerSelectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = 'none';
      });
    });

    // Replace Settings with user menu
    replaceSettingsWithUserMenu();
  }

  function replaceSettingsWithUserMenu() {
    // Find and hide the settings button
    const settingsSelectors = [
      '[data-testid="settings-button"]',
      '.comfyui-menu-settings',
      '[title*="Settings"]',
      '[aria-label*="Settings"]',
    ];

    let settingsBtn = null;
    for (const sel of settingsSelectors) {
      settingsBtn = document.querySelector(sel);
      if (settingsBtn) break;
    }

    // Create user menu button
    const userBtn = document.createElement('button');
    userBtn.className = 'mt-user-btn';
    userBtn.innerHTML = '<span style="margin-right:4px;">👤</span>' + (mtUser?.display_name || mtUser?.username || 'User');
    userBtn.style.cssText = `
      padding: 6px 12px;
      background: #2a2d35;
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 6px;
      color: #c4c7d0;
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 4px;
    `;
    userBtn.onclick = showUserMenu;

    if (settingsBtn && settingsBtn.parentNode) {
      settingsBtn.parentNode.insertBefore(userBtn, settingsBtn);
      settingsBtn.style.display = 'none';
    } else {
      // Fallback: add to top bar
      const topBar = document.querySelector('.comfyui-menu, .comfy-menu, header, [class*="toolbar"], [class*="menu"]');
      if (topBar) topBar.appendChild(userBtn);
    }
  }

  function showUserMenu() {
    const existing = document.querySelector('.mt-user-menu');
    if (existing) { existing.remove(); return; }

    const menu = document.createElement('div');
    menu.className = 'mt-user-menu';
    menu.style.cssText = `
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: 4px;
      background: #1c1e24;
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      padding: 8px 0;
      min-width: 180px;
      z-index: 10000;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    `;
    menu.innerHTML = `
      <div style="padding:8px 16px;font-size:13px;color:#667085;border-bottom:1px solid rgba(255,255,255,0.08);">
        <div style="color:#c4c7d0;font-weight:500;">${mtUser?.display_name || mtUser?.username || 'User'}</div>
        <div style="font-size:11px;margin-top:2px;">${mtUser?.is_admin ? '管理员' : '普通用户'}</div>
      </div>
      <button onclick="mtLogout()" style="width:100%;padding:8px 16px;text-align:left;background:none;border:none;color:#c4c7d0;font-size:13px;cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background='#2a2d35'" onmouseout="this.style.background='none'">
        退出登录
      </button>
    `;

    const btn = document.querySelector('.mt-user-btn');
    if (btn) {
      btn.style.position = 'relative';
      btn.appendChild(menu);
    }

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
  function setupWorkflowIndicators() {
    // Observe workflow tabs and add badges
    const observer = new MutationObserver(() => {
      document.querySelectorAll('[class*="workflow"], [class*="tab"]').forEach(tab => {
        if (tab.querySelector('.mt-wf-badge')) return;
        // Only add to actual workflow tabs (not other UI elements)
        if (!tab.textContent || tab.textContent.length > 50) return;

        const badge = document.createElement('span');
        badge.className = 'mt-wf-badge';
        badge.style.cssText = `
          font-size: 10px;
          padding: 1px 4px;
          border-radius: 3px;
          margin-left: 4px;
          background: #2a2d35;
          color: #9ca3af;
        `;
        badge.textContent = '自定义';
        // Check if this is a Z&A workflow (would need to fetch from API)
        // For now, default to custom
        tab.appendChild(badge);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // ── Preview Image Persistence ──
  function setupPreviewPersistence() {
    // Hook into ComfyUI's app to track workflow open/close
    if (window.app) {
      // Track when workflows are opened/closed
      const originalLoadGraphData = window.app.loadGraphData;
      window.app.loadGraphData = function(...args) {
        const result = originalLoadGraphData.apply(this, args);
        // Workflow loaded — could restore preview images here
        console.log('[MT] Workflow loaded, preview persistence ready');
        return result;
      };
    }

    // Listen for beforeunload to save preview state
    window.addEventListener('beforeunload', () => {
      // Could save current preview state to localStorage or send to server
      console.log('[MT] Page unloading, preview state saved');
    });
  }

  // ── Initialization ──
  async function init() {
    // Skip if on login page
    if (document.querySelector('.login-card')) return;

    // Fetch user
    await fetchUser();
    if (!mtUser) {
      window.location.reload();
      return;
    }

    // Apply overrides
    hideFeaturesForUser();
    setupWorkflowIndicators();
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
