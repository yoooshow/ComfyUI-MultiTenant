"""Frontend injection — inject login UI, lock script, and balance display into ComfyUI."""

import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)

_JS_INJECTED = """(function() {
  'use strict';
  const API_BASE = window.location.origin;
  const WF_NAME = new URLSearchParams(window.location.search).get('workflow') || '';
  var token = localStorage.getItem('token') || localStorage.getItem('mt_token');
  if(token) localStorage.setItem('mt_token', token);
  var mt = localStorage.getItem('mt_token');
  if(!mt) {
    document.documentElement.innerHTML='<div id="mt-login" style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:#1a1d23;color:#fff;font-family:sans-serif;flex-direction:column"><h1 style="font-size:24px;font-weight:700;letter-spacing:-0.02em;margin-bottom:8px">ComfyUI <span style="opacity:0.5;font-weight:400">\u591a\u79df\u6237</span></h1><div style="background:#25262b;padding:32px;border-radius:12px;width:340px;margin-top:12px"><input id="mt-u" placeholder="\\u7528\\u6237\\u540d" style="width:100%;padding:10px 14px;margin-bottom:12px;border:1px solid #373a40;border-radius:6px;background:#1a1d23;color:#fff;font-size:14px"><input id="mt-p" type="password" placeholder="\\u5bc6\\u7801" style="width:100%;padding:10px 14px;margin-bottom:16px;border:1px solid #373a40;border-radius:6px;background:#1a1d23;color:#fff;font-size:14px"><button onclick="(function(){var u=document.getElementById(\\'mt-u\\').value;var p=document.getElementById(\\'mt-p\\').value;fetch(\\'/api/auth/login\\',{method:\\'POST\\',headers:{\\"Content-Type\\":\\"application/json\\"},body:JSON.stringify({username:u,password:p})}).then(function(r){return r.json()}).then(function(d){if(d.access_token){localStorage.setItem(\\'mt_token\\',d.access_token);location.reload()}else{alert(d.detail||\\'\\u767b\\u5f55\\u5931\\u8d25\\')}}).catch(function(e){alert(\\'\\u7f51\\u7edc\\u9519\\u8bef: \\'+e.message)})})()" style="width:100%;padding:10px;background:#4f6ef7;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer">\\u767b\\u5f55</button><p style="color:#667085;font-size:12px;margin-top:12px;text-align:center">\\u9ed8\\u8ba4: admin / admin123</p></div></div>';return;
  }
  fetch(API_BASE+'/api/users/me/balance',{headers:{'Authorization':'Bearer '+mt}}).then(function(r){return r.json()}).then(function(d){var e=document.getElementById('mt-bal');if(e)e.textContent='\\u901a\\u8bc1: '+(d.token_balance||0)}).catch(function(){});
  var de=document.createElement('div');de.id='mt-bal';de.style.cssText='position:fixed;bottom:12px;left:12px;z-index:99999;background:rgba(0,0,0,0.75);color:#fff;padding:8px 14px;border-radius:6px;font-size:13px;font-family:sans-serif;backdrop-filter:blur(4px);pointer-events:none';de.textContent='\\u901a\\u8bc1: ---';document.body.appendChild(de);
  setInterval(function(){fetch(API_BASE+'/api/users/me/balance',{headers:{'Authorization':'Bearer '+localStorage.getItem('mt_token')}}).then(function(r){return r.json()}).then(function(d){var e=document.getElementById('mt-bal');if(e)e.textContent='\\u901a\\u8bc1: '+(d.token_balance||0)}).catch(function(){})},15000);
  var _f=window.fetch;window.fetch=function(u,o){if(o&&o.method==='POST'&&typeof u==='string'&&(u.indexOf('/prompt')>=0||u.indexOf('/queue')>=0)){return function(u,o){var b;try{b=JSON.parse(o.body)}catch(e){return _f.apply(this,arguments)};var t=localStorage.getItem('mt_token');if(!t){return new Response('{"error":"\\u8bf7\\u5148\\u767b\\u5f55"}',{status:401,headers:{'Content-Type':'application/json'}})};var w=b.prompt||b;return fetch(API_BASE+'/api/workspace/execute',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+t},body:JSON.stringify({workflow_name:WF_NAME||'unknown',workflow_data:w})}).then(function(r){return r.json()}).then(function(d){if(!d.prompt_id){return new Response(JSON.stringify(d),{status:402,headers:{'Content-Type':'application/json'}})};var e=document.getElementById('mt-bal');if(e)e.textContent='\\u901a\\u8bc1: '+(d.token_balance||'?');return new Response(JSON.stringify({prompt_id:d.prompt_id,number:1,node_errors:{}}),{status:200,headers:{'Content-Type':'application/json'}})})}}(u,o)};return _f.apply(this,arguments)};
})();"""


def inject_frontend(server):
    """Register a route handler for / that injects our scripts into index.html."""
    web_root = getattr(server, 'web_root', None)
    if not web_root:
        logger.warning("server.web_root not found, cannot inject frontend")
        return

    async def injected_index_handler(request):
        """Serve index.html with injected auth/balance/lock scripts."""
        idx_path = os.path.join(web_root, "index.html")
        if not os.path.exists(idx_path):
            raise web.HTTPNotFound()

        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                html = f.read()

            # Inject scripts before </head> and before </body>
            script_tag = f'<script id="mt-bridge">{_JS_INJECTED}</script>'

            if "</head>" in html:
                html = html.replace("</head>", f'{script_tag}\n</head>')
            else:
                html = script_tag + "\n" + html

            return web.Response(text=html, content_type="text/html")
        except Exception as e:
            logger.error(f"Failed to inject index.html: {e}")
            raise web.HTTPInternalServerError()

    # Register our handler for / — takes priority over web.static()
    server.app.router.add_get("/", injected_index_handler)
    # Also handle /index.html
    server.app.router.add_get("/index.html", injected_index_handler)

    logger.info(f"Frontend injection registered for {web_root}")
