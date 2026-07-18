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

    # Register admin panel route
    try:
        inject_admin_route(server)
    except Exception as e:
        logger.error(f'Admin panel setup error: {e}')

# ── Admin Panel HTML (served at /admin) ──
_ADMIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ComfyUI 管理后台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans SC",sans-serif;background:#f5f6fa;color:#1a1d23;min-height:100vh}
.navbar{display:flex;align-items:center;gap:1rem;padding:0 2rem;height:56px;background:#1a1d23;color:#fff;position:sticky;top:0;z-index:100}
.navbar .brand{font-weight:700;font-size:1.1rem;flex:1}
.navbar .brand a{color:#fff;text-decoration:none}
.navbar .user-info{display:flex;align-items:center;gap:.75rem;font-size:.9rem}
.navbar .user-info .bal{background:rgba(79,110,247,.2);border:1px solid rgba(79,110,247,.35);border-radius:20px;padding:.25rem .7rem;font-size:.8rem;font-weight:600}
.btn{display:inline-flex;align-items:center;gap:.4rem;padding:.45rem 1rem;border:none;border-radius:6px;font-size:.85rem;font-weight:500;cursor:pointer;white-space:nowrap;transition:all .15s}
.btn-primary{background:#4f6ef7;color:#fff}
.btn-primary:hover{background:#3d5bd9}
.btn-danger{background:#e74c3c;color:#fff}
.btn-sm{padding:.3rem .6rem;font-size:.8rem}
.btn-outline{background:transparent;border:1px solid #d0d5dd;color:#1a1d23}
.btn-outline:hover{background:#f0f2f5}
.container{max-width:1100px;margin:0 auto;padding:2rem}
h1{font-size:1.4rem;font-weight:700;margin-bottom:1.25rem}
.tabs{display:flex;gap:.25rem;margin-bottom:1.25rem;border-bottom:1px solid #e2e5ea;padding-bottom:0}
.tab{background:none;border:none;border-bottom:2px solid transparent;padding:.6rem 1rem;font-size:.9rem;color:#667085;cursor:pointer;transition:all .15s;margin-bottom:-1px}
.tab:hover{color:#1a1d23}
.tab.active{color:#4f6ef7;border-bottom-color:#4f6ef7;font-weight:600}
.card{background:#fff;border:1px solid #e2e5ea;border-radius:8px;padding:1.25rem 1.5rem;margin-bottom:1rem}
.card-hdr{font-size:1rem;font-weight:600;margin-bottom:.75rem;display:flex;align-items:center;justify-content:space-between}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{padding:.6rem .75rem;text-align:left;border-bottom:1px solid #e2e5ea}
th{font-weight:600;color:#667085;font-size:.8rem;text-transform:uppercase}
tr:hover td{background:#f9fafb}
input,select{width:100%;padding:.5rem .7rem;border:1px solid #d0d5dd;border-radius:6px;font-size:.9rem}
input:focus{outline:none;border-color:#4f6ef7}
.form-row{display:flex;gap:.75rem;margin-bottom:.75rem;align-items:flex-end}
.form-row>*{flex:1}
.form-row .btn{flex:0 0 auto}
.empty{text-align:center;color:#98a2b3;padding:2rem}
.badge{display:inline-block;padding:.15rem .5rem;border-radius:20px;font-size:.78rem;font-weight:500}
.badge-admin{background:#dbeafe;color:#1d4ed8}
.badge-user{background:#f0f2f5;color:#667085}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:200;display:none}
.modal{background:#fff;border-radius:12px;padding:1.5rem 2rem;width:90%;max-width:520px;max-height:85vh;overflow-y:auto}
.modal h2{font-size:1.15rem;font-weight:600;margin-bottom:1rem}
.modal-close{float:right;background:none;border:none;font-size:1.25rem;cursor:pointer;color:#667085;padding:0}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem;margin-bottom:1rem}
.stat-card{background:#fff;border:1px solid #e2e5ea;border-radius:8px;padding:1.25rem;text-align:center}
.stat-card .num{font-size:1.75rem;font-weight:700}
.stat-card .lbl{font-size:.85rem;color:#667085;margin-top:.2rem}
.loading{text-align:center;padding:2rem;color:#98a2b3}
.toast-fixed{position:fixed;top:1rem;right:1rem;z-index:300;padding:.75rem 1.25rem;border-radius:8px;color:#fff;font-size:.9rem;box-shadow:0 4px 12px rgba(0,0,0,.15)}@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
</style>
</head>
<body>
<div class="navbar">
  <div class="brand"><a href="/">ComfyUI</a> 管理后台</div>
  <div class="user-info">
    <span class="bal" id="nav-bal">通证: ---</span>
    <span id="nav-user"></span>
    <button class="btn btn-sm btn-outline" onclick="location.href='/'">返回工作台</button>
  </div>
</div>
<div class="container">
  <div id="tab-nav" class="tabs">
    <button class="tab active" data-tab="users">用户管理</button>
    <button class="tab" data-tab="workflows">工作流模板</button>
    <button class="tab" data-tab="stats">系统统计</button>
    <button class="tab" data-tab="transactions">交易记录</button>
  </div>
  <div id="tab-content">正在加载...</div>
</div>
<div id="modal" class="modal-overlay"><div class="modal"><button class="modal-close" onclick="hideModal()">&times;</button><div id="modal-body"></div></div></div>
<script>
var API_BASE = window.location.origin;
var token = localStorage.getItem('mt_token');

function toast(msg,type){var d=document.createElement('div');d.className='toast-fixed';d.style.background=type==='error'?'#ef4444':'#10b981';d.textContent=msg;document.body.appendChild(d);setTimeout(function(){d.remove()},3000)}
function api(m,p,b){return fetch(API_BASE+p,{method:m||'GET',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:b?JSON.stringify(b):null}).then(function(r){if(r.status===401){location.href='/'}if(r.status===204)return null;return r.json()})}
function showModal(html){document.getElementById('modal-body').innerHTML=html;document.getElementById('modal').style.display=''}
function hideModal(){document.getElementById('modal').style.display='none'}
function switchTab(tab){document.querySelectorAll('.tab').forEach(function(t){t.classList.toggle('active',t.dataset.tab===tab)});renderTab(tab)}

function getTok(){return localStorage.getItem('mt_token')||''}
function renderTab(tab){
  var el=document.getElementById('tab-content');el.innerHTML='<div class="loading">加载中...</div>';
  if(tab==='users')renderUsers(el);
  else if(tab==='workflows')renderWorkflows(el);
  else if(tab==='stats')renderStats(el);
  else if(tab==='transactions')renderTransactions(el);
}

function renderUsers(el){
  api('GET','/api/admin/users').then(function(d){
    var items=d.items||[];
    var rows=items.map(function(u){
      var badge=u.is_admin?'<span class="badge badge-admin">管理员</span>':'<span class="badge badge-user">用户</span>';
      return '<tr><td>#'+u.id+'</td><td>'+u.username+'</td><td>'+u.display_name+'</td><td>'+u.token_balance.toLocaleString()+'</td><td>'+badge+'</td><td>'+new Date(u.created_at).toLocaleDateString()+'</td><td><button class="btn btn-sm btn-outline" onclick="adjustTokens('+u.id+',\\''+u.username+'\\','+u.token_balance+')">调额</button></td></tr>';
    }).join('');
    el.innerHTML='<div class="card"><div class="card-hdr"><span>用户列表</span><button class="btn btn-primary btn-sm" onclick="showCreateUser()">+ 添加用户</button></div><div class="table-wrapper"><table><thead><tr><th>ID</th><th>用户名</th><th>显示名</th><th>通证</th><th>角色</th><th>创建时间</th><th></th></tr></thead><tbody>'+(rows||'<tr><td colspan="7"><div class="empty">暂无用户</div></td></tr>')+'</tbody></table></div></div>';
  }).catch(function(e){el.innerHTML='<div class="empty">加载失败: '+e.message+'</div>'});
}

function showCreateUser(){
  showModal('<h2>添加用户</h2><div class="form-row"><input id=cu-u placeholder="用户名"></div><div class="form-row"><input id=cu-p type=password placeholder="密码"></div><div class="form-row"><input id=cu-d placeholder="显示名"></div><div class="form-row"><input id=cu-t type=number value=0 placeholder="初始通证"></div><div class="form-row"><label><input id=cu-a type=checkbox> 管理员</label></div><div class="form-row"><button class="btn btn-primary" onclick="createUser()">创建</button><button class="btn btn-outline" onclick="hideModal()">取消</button></div>');
}
function createUser(){
  api('POST','/api/admin/users',{username:document.getElementById('cu-u').value,password:document.getElementById('cu-p').value,display_name:document.getElementById('cu-d').value,token_balance:parseInt(document.getElementById('cu-t').value)||0,is_admin:document.getElementById('cu-a').checked}).then(function(){hideModal();toast('用户创建成功');renderTab('users')}).catch(function(e){toast(e.message,'error')});
}

function adjustTokens(id,name,bal){
  showModal('<h2>调整通证: '+name+'</h2><p style="color:#667085;font-size:.85rem;margin-bottom:.75rem">当前余额: '+bal.toLocaleString()+'</p><div class="form-row"><input id=at-a type=number value=0 placeholder="数量(正加负扣)"></div><div class="form-row"><input id=at-d placeholder="备注"></div><div class="form-row"><button class="btn btn-primary" onclick="doAdjust('+id+')">确认</button><button class="btn btn-outline" onclick="hideModal()">取消</button></div>');
}
function doAdjust(id){
  api('POST','/api/admin/users/'+id+'/tokens',{user_id:id,amount:parseInt(document.getElementById('at-a').value)||0,description:document.getElementById('at-d').value||'管理员调整'}).then(function(d){hideModal();toast('调整成功，余额: '+d.token_balance);renderTab('users')}).catch(function(e){toast(e.message,'error')});
}

function renderWorkflows(el){
  api('GET','/api/admin/workflows').then(function(items){
    items=items||[];
    var rows=items.map(function(w){
      return '<tr><td>#'+w.id+'</td><td>'+w.display_name+'</td><td><code style="font-size:.8rem">'+w.name+'</code></td><td>'+w.base_cost+'</td><td>'+w.cost_per_step+'</td><td>'+w.cost_per_megapixel+'</td><td>'+(w.is_active?'<span style="color:#059669">启用</span>':'<span style="color:#98a2b3">禁用</span>')+'</td><td><button class="btn btn-sm btn-danger" onclick="deleteWorkflow('+w.id+',\\''+w.display_name+'\\')">删除</button></td></tr>';
    }).join('');
    el.innerHTML='<div class="card"><div class="card-hdr"><span>工作流模板</span><button class="btn btn-primary btn-sm" onclick="showUploadWorkflow()">+ 上传 JSON</button></div><div class="table-wrapper"><table><thead><tr><th>ID</th><th>名称</th><th>标识</th><th>基础费</th><th>步数费</th><th>MP费</th><th>状态</th><th></th></tr></thead><tbody>'+(rows||'<tr><td colspan="8"><div class="empty">暂无模板</div></td></tr>')+'</tbody></table></div></div>';
  }).catch(function(e){el.innerHTML='<div class="empty">加载失败: '+e.message+'</div>'});
}

function showUploadWorkflow(){
  showModal('<h2>上传工作流</h2><div class="form-row"><input id=wf-f type=file accept=.json></div><div class="form-row"><input id=wf-n placeholder="标识(默认文件名)"></div><div class="form-row"><input id=wf-dn placeholder="显示名称(默认文件名)"></div><div class="form-row"><input id=wf-bc type=number value=10 placeholder="基础费用"></div><div class="form-row"><input id=wf-cps type=number value=1 placeholder="步数费用"></div><div class="form-row"><input id=wf-cmp type=number value=5 placeholder="MP费用"></div><div class="form-row"><button class="btn btn-primary" onclick="uploadWorkflow()">上传</button><button class="btn btn-outline" onclick="hideModal()">取消</button></div>');
}
function uploadWorkflow(){
  var file=document.getElementById('wf-f').files[0];if(!file){toast('请选择文件','error');return}
  var name=document.getElementById('wf-n').value||file.name.replace(/\\.json$/,'');
  var display_name=document.getElementById('wf-dn').value||name;
  var base_cost=parseInt(document.getElementById('wf-bc').value)||10;
  var cost_per_step=parseInt(document.getElementById('wf-cps').value)||1;
  var cost_per_megapixel=parseInt(document.getElementById('wf-cmp').value)||5;
  var reader=new FileReader();
  reader.onload=function(ev){
    var data;try{data=JSON.parse(ev.target.result)}catch(e){toast('JSON格式错误','error');return}
    api('POST','/api/admin/workflows',{name:name,display_name:display_name,base_cost:base_cost,cost_per_step:cost_per_step,cost_per_megapixel:cost_per_megapixel,comfyui_workflow:data}).then(function(){hideModal();toast('上传成功');renderTab('workflows')}).catch(function(e){toast(e.message,'error')});
  };reader.readAsText(file);
}
function deleteWorkflow(id,name){
  if(!confirm('确定删除工作流 "'+name+'" ？'))return;
  api('DELETE','/api/admin/workflows/'+id).then(function(){toast('已删除');renderTab('workflows')}).catch(function(e){toast(e.message,'error')});
}

function renderStats(el){
  api('GET','/api/admin/stats').then(function(d){
    el.innerHTML='<div class="stats-grid"><div class="stat-card"><div class="num">'+d.total_users+'</div><div class="lbl">用户数</div></div><div class="stat-card"><div class="num">'+d.total_transactions+'</div><div class="lbl">交易数</div></div><div class="stat-card"><div class="num">'+d.total_tokens_consumed.toLocaleString()+'</div><div class="lbl">消耗通证</div></div></div>';
  }).catch(function(e){el.innerHTML='<div class="empty">加载失败: '+e.message+'</div>'});
}

function renderTransactions(el){
  api('GET','/api/users/me/transactions?page=1&page_size=50').then(function(d){
    var items=d.items||[];
    var rows=items.map(function(t){
      var sign=t.amount>0?'<span style="color:#059669">+'+t.amount+'</span>':'<span style="color:#ef4444">'+t.amount+'</span>';
      return '<tr><td>'+t.transaction_type+'</td><td>'+sign+'</td><td>'+t.balance_after+'</td><td>'+t.description+'</td><td>'+new Date(t.created_at).toLocaleString()+'</td></tr>';
    }).join('');
    el.innerHTML='<div class="card"><div class="card-hdr"><span>交易记录</span></div><div class="table-wrapper"><table><thead><tr><th>类型</th><th>数量</th><th>余额</th><th>说明</th><th>时间</th></tr></thead><tbody>'+(rows||'<tr><td colspan="5"><div class="empty">暂无记录</div></td></tr>')+'</tbody></table></div></div>';
  }).catch(function(e){el.innerHTML='<div class="empty">加载失败: '+e.message+'</div>'});
}

// Init
if(!token){location.href='/'}else{
  (function(){fetch('/api/auth/me',{headers:{'Authorization':'Bearer '+token}}).then(function(r){return r.json()}).then(function(u){
    document.getElementById('nav-user').textContent=u.display_name||u.username;
    if(!u.is_admin){document.getElementById('tab-content').innerHTML='<div class="empty">需要管理员权限</div>';return}
    renderTab('users');
    // Update balance
    fetch('/api/users/me/balance',{headers:{'Authorization':'Bearer '+token}}).then(function(r){return r.json()}).then(function(d){document.getElementById('nav-bal').textContent='通证: '+d.token_balance.toLocaleString()})
  }).catch(function(){location.href='/'})})();
}
document.querySelectorAll('.tab').forEach(function(t){t.addEventListener('click',function(){switchTab(t.dataset.tab)})});
</script>
</body>
</html>"""


def inject_admin_route(server):
    """Register the /admin route for the admin panel."""
    from .auth import verify_token

    async def admin_handler(request):
        # Check auth
        token = request.headers.get("Authorization", "").replace("Bearer ", "") or request.query.get("token", "")
        if not token:
            return web.HTTPFound("/")  # redirect to login
        payload = verify_token(token)
        if not payload:
            return web.HTTPFound("/")

        # Serve the admin panel HTML
        return web.Response(text=_ADMIN_PAGE, content_type="text/html")

    server.app.router.add_get("/admin", admin_handler)
    logger.info("Admin panel registered at /admin")
