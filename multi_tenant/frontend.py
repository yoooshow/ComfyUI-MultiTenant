"""Frontend injection — inject login UI, lock script, and balance display into ComfyUI."""

import logging
import os

logger = logging.getLogger(__name__)

_INJECTED = {
    "lock_js": None,
    "style_css": None,
}


def _load_static(filename: str) -> str:
    """Load a static file from the multi_tenant/static directory."""
    dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    filepath = os.path.join(dir_path, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Static file not found: {filepath}")
        # Return inline content directly
        if filename == "lock.js":
            return _DEFAULT_LOCK_JS
        elif filename == "style.css":
            return _DEFAULT_STYLE_CSS
        return ""


_DEFAULT_LOCK_JS = r"""
(function() {
  'use strict';
  const API_BASE = window.location.origin;
  const WF_NAME = new URLSearchParams(window.location.search).get('workflow') || '';

  // ── Auth check ──
  if (!localStorage.getItem('mt_token')) {
    document.body.innerHTML = '<div id="mt-login" style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:#1a1d23;color:#fff;font-family:sans-serif"><div style="text-align:center"><h2>请先登录</h2><p style="color:#98a2b3;margin-top:8px">在主页登录后再访问 ComfyUI 工作台</p></div></div>';
    return;
  }

  // ── Balance display ──
  function updateBalance() {
    fetch(API_BASE + '/api/users/me/balance', {
      headers: { 'Authorization': 'Bearer ' + localStorage.getItem('mt_token') }
    }).then(function(r) { return r.json(); }).then(function(d) {
      var el = document.getElementById('mt-balance');
      if (el) el.textContent = '通证: ' + (d.token_balance || 0);
    }).catch(function() {});
  }

  var balanceEl = document.createElement('div');
  balanceEl.id = 'mt-balance';
  balanceEl.style.cssText = 'position:fixed;bottom:12px;left:12px;z-index:99999;background:rgba(0,0,0,0.75);color:#fff;padding:8px 14px;border-radius:6px;font-size:13px;font-family:sans-serif;backdrop-filter:blur(4px);pointer-events:none';
  balanceEl.textContent = '通证: ---';
  document.body.appendChild(balanceEl);
  updateBalance();
  setInterval(updateBalance, 15000);

  // ── Queue intercept for billing ──
  var _origFetch = window.fetch;
  window.fetch = function(url, options) {
    if (options && options.method === 'POST' && typeof url === 'string' && url.indexOf('/prompt') >= 0) {
      return handleQueue(_origFetch, url, options);
    }
    return _origFetch.apply(this, arguments);
  };

  function showToast(msg, type) {
    var d = document.createElement('div');
    d.style.cssText = 'position:fixed;top:16px;right:16px;z-index:99999;padding:12px 20px;border-radius:8px;font-size:14px;font-weight:500;box-shadow:0 4px 16px rgba(0,0,0,0.25);color:#fff;max-width:400px;' + (type === 'error' ? 'background:#ef4444;' : 'background:#10b981;');
    d.textContent = msg;
    document.body.appendChild(d);
    setTimeout(function() { d.remove(); }, 4000);
  }

  async function handleQueue(_origFetch, url, options) {
    var body;
    try { body = JSON.parse(options.body); } catch(e) { return _origFetch.apply(this, arguments); }
    var token = localStorage.getItem('mt_token');
    if (!token) { showToast('请先登录', 'error'); return new Response('{"error":"No auth"}', {status:401, headers:{'Content-Type':'application/json'}}); }

    var workflowData = body.prompt || body;
    try {
      var resp = await _origFetch(API_BASE + '/api/workspace/execute', {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+token},
        body: JSON.stringify({ workflow_name: WF_NAME || 'unknown', workflow_data: workflowData })
      });
      var result = await resp.json();
      if (resp.ok) {
        showToast('已提交，执行成功后扣费 '+result.token_cost+' 通证');
        updateBalance();
        return new Response(JSON.stringify({prompt_id:result.prompt_id, number:1, node_errors:{}}), {status:200, headers:{'Content-Type':'application/json'}});
      } else {
        showToast(result.detail || '提交失败', 'error');
        return new Response(JSON.stringify(result), {status:resp.status, headers:{'Content-Type':'application/json'}});
      }
    } catch(e) {
      showToast('请求失败: '+e.message, 'error');
      return _origFetch.apply(this, arguments);
    }
  }
})();
"""

_DEFAULT_STYLE_CSS = """#mt-balance { user-select: none; opacity: 0.9; transition: opacity 0.3s; }
#mt-balance:hover { opacity: 1; }
#mt-login h2 { margin-bottom: 12px; font-weight: 600; }
"""


def inject_frontend(server):
    """Hook into FrontendManager to inject our scripts into HTML responses.

    This adds a middleware that injects our login UI, lock script, and
    balance display into every HTML page served by ComfyUI.
    """
    # The ComfyUI FrontendManager serves the frontend via routes.
    # We can inject into the response by adding an on_prepare signal
    # or by modifying how the frontend index.html is served.

    # Strategy: register a middleware that intercepts HTML responses
    # and injects our scripts after the closing </body> tag.

    current_middlewares = list(server.app.middlewares) if hasattr(server.app, 'middlewares') else []

    @web.middleware
    async def inject_html_middleware(request, handler):
        response = await handler(request)
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type and response.status == 200:
            body = response.body
            if body:
                try:
                    html = body.decode("utf-8", errors="replace")
                    lock_js = _DEFAULT_LOCK_JS
                    style_css = _DEFAULT_STYLE_CSS

                    # Add auth token management script (injected into <head>)
                    token_script = (
                        '<script id="mt-auth-bridge">'
                        '(function(){'
                        'var t = localStorage.getItem("token");'
                        'if(t && !localStorage.getItem("mt_token")) localStorage.setItem("mt_token", t);'
                        'var mt = localStorage.getItem("mt_token");'
                        'if(!mt){'
                        '  var html=document.documentElement;'
                        '  html.innerHTML=\'<div id="mt-login" style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:#1a1d23;color:#fff;font-family:sans-serif;flex-direction:column;gap:20px">'
                        '<h1 style="font-size:24px;font-weight:700;letter-spacing:-0.02em">ComfyUI <span style="opacity:0.5">多租户</span></h1>'
                        '<div id="mt-login-form" style="background:#25262b;padding:32px;border-radius:12px;width:340px">'
                        '<input id="mt-login-user" placeholder="用户名" style="width:100%;padding:10px 14px;margin-bottom:12px;border:1px solid #373a40;border-radius:6px;background:#1a1d23;color:#fff;font-size:14px">'
                        '<input id="mt-login-pass" type="password" placeholder="密码" style="width:100%;padding:10px 14px;margin-bottom:16px;border:1px solid #373a40;border-radius:6px;background:#1a1d23;color:#fff;font-size:14px">'
                        '<button id="mt-login-btn" style="width:100%;padding:10px;background:#4f6ef7;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer">登录</button>'
                        '<p id="mt-login-error" style="color:#ef4444;font-size:13px;margin-top:10px;display:none"></p>'
                        '<p style="color:#667085;font-size:12px;margin-top:12px;text-align:center">默认管理员: admin / admin123</p>'
                        '</div></div>\';'
                        '  document.getElementById("mt-login-btn").onclick=function(){'
                        '    var u=document.getElementById("mt-login-user").value;'
                        '    var p=document.getElementById("mt-login-pass").value;'
                        '    fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:u,password:p})})'
                        '    .then(function(r){return r.json()}).then(function(d){'
                        '      if(d.access_token){localStorage.setItem("mt_token",d.access_token);location.reload();}'
                        '      else{document.getElementById("mt-login-error").textContent=d.detail||"登录失败";document.getElementById("mt-login-error").style.display="";}'
                        '    }).catch(function(){document.getElementById("mt-login-error").textContent="网络错误";document.getElementById("mt-login-error").style.display="";});'
                        '  };'
                        '}'
                        '})();'
                        '</script>'
                    )
                    # Lock + balance script (injected before </body>)
                    lock_tag = f'<script id="mt-lock">{lock_js}</script>'
                    style_tag = f'<style id="mt-style">{style_css}</style>'

                    if "</head>" in html:
                        html = html.replace("</head>", f"{token_script}\n{style_tag}\n</head>")
                    elif "</body>" in html:
                        html = html.replace("</body>", f"{token_script}\n{style_tag}\n</body>")
                    else:
                        html = f"{token_script}\n{style_tag}\n{html}"

                    if "</body>" in html:
                        html = html.replace("</body>", f"{lock_tag}\n</body>")
                    else:
                        html = f"{html}\n{lock_tag}"

                    response.body = html.encode("utf-8")
                    response.headers["Content-Length"] = str(len(response.body))
                except Exception as e:
                    logger.debug(f"HTML injection failed: {e}")
        return response

    # Add the middleware to the app
    server.app.middlewares.append(inject_html_middleware)
    logger.info("Frontend injection middleware registered")
