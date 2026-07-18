"""Frontend injection — serve login page for unauthenticated users, lock/billing JS for authenticated."""

import json
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)

# ── Static HTML for the login page (served when no valid auth token) ──
_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ComfyUI 多租户</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif; background: #1a1d23; color: #fff; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.login-container { text-align: center; width: 100%; max-width: 380px; padding: 20px; }
h1 { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 4px; }
h1 span { font-weight: 400; opacity: 0.5; }
.subtitle { color: #667085; font-size: 14px; margin-bottom: 28px; }
.form-card { background: #25262b; padding: 28px; border-radius: 12px; text-align: left; }
input { width: 100%; padding: 10px 14px; margin-bottom: 12px; border: 1px solid #373a40; border-radius: 6px; background: #1a1d23; color: #fff; font-size: 14px; outline: none; }
input:focus { border-color: #4f6ef7; }
button { width: 100%; padding: 10px; background: #4f6ef7; color: #fff; border: none; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }
button:hover { background: #3d5bd9; }
button:disabled { opacity: 0.6; cursor: not-allowed; }
.error { color: #ef4444; font-size: 13px; margin-top: 8px; display: none; }
.hint { color: #667085; font-size: 12px; margin-top: 12px; text-align: center; }
</style>
</head>
<body>
<div class="login-container">
  <h1>ComfyUI <span>多租户</span></h1>
  <p class="subtitle">请登录以使用工作台</p>
  <div class="form-card">
    <input id="mt-u" placeholder="用户名" autocomplete="username">
    <input id="mt-p" type="password" placeholder="密码" autocomplete="current-password">
    <button id="mt-btn" onclick="doLogin()">登录</button>
    <div id="mt-err" class="error"></div>
    <p class="hint">默认: admin / admin123</p>
  </div>
</div>
<script>
function doLogin(){
  var u=document.getElementById('mt-u').value;
  var p=document.getElementById('mt-p').value;
  var btn=document.getElementById('mt-btn');
  var err=document.getElementById('mt-err');
  btn.disabled=true; btn.textContent='登录中...';
  fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})})
  .then(function(r){return r.json()})
  .then(function(d){
    if(d.access_token){
      localStorage.setItem('mt_token',d.access_token);
      window.location.href='/?'+new URLSearchParams({token:d.access_token});
    } else {
      err.textContent=d.detail||'登录失败';
      err.style.display='';
      btn.disabled=false; btn.textContent='登录';
    }
  })
  .catch(function(e){
    err.textContent='网络错误: '+e.message;
    err.style.display='';
    btn.disabled=false; btn.textContent='登录';
  });
}
document.getElementById('mt-u').addEventListener('keydown',function(e){if(e.key==='Enter'){document.getElementById('mt-p').focus()}});
document.getElementById('mt-p').addEventListener('keydown',function(e){if(e.key==='Enter'){doLogin()}});
document.getElementById('mt-u').focus();
</script>
</body>
</html>"""

# ── Lock/Billing JS injected into ComfyUI for authenticated users ──
_LOCK_JS = """
(function(){
var mt=localStorage.getItem('mt_token');
if(!mt) return;
fetch('/api/users/me/balance',{headers:{'Authorization':'Bearer '+mt}}).then(function(r){return r.json()}).then(function(d){
  var e=document.getElementById('mt-bal');if(e)e.textContent='\\u901a\\u8bc1: '+(d.token_balance||0);
}).catch(function(){});
var de=document.createElement('div');de.id='mt-bal';de.style.cssText='position:fixed;bottom:12px;left:12px;z-index:99999;background:rgba(0,0,0,0.75);color:#fff;padding:8px 14px;border-radius:6px;font-size:13px;backdrop-filter:blur(4px);pointer-events:none';de.textContent='\\u901a\\u8bc1: ---';document.body.appendChild(de);
var _f=window.fetch;window.fetch=function(u,o){if(o&&o.method==='POST'&&typeof u==='string'&&(u.indexOf('/prompt')>=0||u.indexOf('/queue')>=0)){
  var b;try{b=JSON.parse(o.body)}catch(e){return _f.apply(this,arguments)}
  var t=localStorage.getItem('mt_token');if(!t){return new Response('{}',{status:401})}
  return fetch('/api/workspace/execute',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+t},body:JSON.stringify({workflow_data:b.prompt||b})})
  .then(function(r){return r.json()}).then(function(d){
    var e=document.getElementById('mt-bal');if(e)e.textContent='\\u901a\\u8bc1: '+(d.token_balance||'?');
    return new Response(JSON.stringify({prompt_id:d.prompt_id,number:1,node_errors:{}}),{status:200,headers:{'Content-Type':'application/json'}});
  }).catch(function(){return _f.apply(this,arguments)});
}return _f.apply(this,arguments)};
})();
"""


def inject_frontend(server):
    """Register route handlers for frontend auth + lock script injection."""
    web_root = getattr(server, 'web_root', None)
    if not web_root:
        logger.warning("server.web_root not found, cannot inject frontend")
        return

    # Import auth for token verification
    from .auth import verify_token

    async def root_handler(request):
        """Serve: login page if unauthenticated, or ComfyUI with lock scripts."""
        # Check for valid auth token first
        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        if not token:
            token = request.query.get("token", "")
        if token:
            payload = verify_token(token)
            # If token is valid, also store mt_token for JS to pick up
            if payload:
                # Serve the regular index.html with lock scripts injected
                idx_path = os.path.join(web_root, "index.html")
                if not os.path.exists(idx_path):
                    return web.HTTPNotFound()
                try:
                    with open(idx_path, "r", encoding="utf-8") as f:
                        html = f.read()
                    # Inject mt_token for the lock script to pick up + clean URL
                    token_script = f'<script>localStorage.setItem("mt_token","{token}");if(location.search.includes("token="))history.replaceState({{}},"",location.pathname)</script>'
                    lock_script = f'<script id="mt-lock">{_LOCK_JS}</script>'
                    if "</head>" in html:
                        html = html.replace("</head>", f"{token_script}\n</head>")
                    if "</body>" in html:
                        html = html.replace("</body>", f"{lock_script}\n</body>")
                    return web.Response(text=html, content_type="text/html")
                except Exception as e:
                    logger.error(f"Failed to serve index.html: {e}")
                    return web.HTTPInternalServerError()

        # No valid token — serve login page
        html = _LOGIN_PAGE
        # If there's a token in query param (e.g. from external redirect), pass it to JS
        if token:
            # Token was provided but invalid - add error message
            html = html.replace(
                '<div id="mt-err" class="error"></div>',
                '<div id="mt-err" class="error" style="display:">登录已过期，请重新登录</div>',
            )
        return web.Response(text=html, content_type="text/html")

    # Register our handler for / and /index.html (takes priority over web.static)
    server.app.router.add_get("/", root_handler)
    server.app.router.add_get("/index.html", root_handler)

    logger.info(f"Frontend injection registered for {web_root}")
