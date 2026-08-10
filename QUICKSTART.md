# ComfyUI 启动备忘

本机有两套互不影响的 ComfyUI：

| 实例 | 目录 | 端口 | 用途 |
|---|---|---|---|
| 多租户版 | `~/ComfyUI-MultiTenant` | 8188 | 正式给用户用：登录 / 计费 / 顶栏 |
| 原版测试版 | `~/ComfyUI-Vanilla` | 8189 | 调试、装节点，可随时跟随官方更新 |

---

## 多租户版（8188）

```bash
cd ~/ComfyUI-MultiTenant
bash setup.sh
```

- 登录页：`http://<本机IP>:8188`
- 管理员：`admin / admin123`（后台 `/admin?token=...` 或顶栏"管理"）
- 普通用户注册后需管理员在后台发放 Token 才能登录
- 管理员顶栏有"原版入口" `/raw`，可跳过多租户直接看原生 ComfyUI

停止：

```bash
pkill -f "port 8188"
```

---

## 原版测试版（8189）

```bash
# 首次安装（自动建 venv + 装依赖 + 装 Manager + 启动）
bash ~/ComfyUI-MultiTenant/install_vanilla.sh

# 之后单独启动
bash ~/ComfyUI-MultiTenant/start_vanilla.sh        # 前台，Ctrl+C 停止
bash ~/ComfyUI-MultiTenant/start_vanilla.sh --bg   # 后台

# 常用控制
bash ~/ComfyUI-MultiTenant/start_vanilla.sh stop       # 停止
bash ~/ComfyUI-MultiTenant/start_vanilla.sh restart    # 后台重启
bash ~/ComfyUI-MultiTenant/start_vanilla.sh status     # 查看状态

# 跟随官方更新（停止 -> git pull -> 装依赖 -> 重启）
bash ~/ComfyUI-MultiTenant/update_vanilla.sh
```

自定义目录/端口：

```bash
bash ~/ComfyUI-MultiTenant/install_vanilla.sh /Users/comfyui/ComfyUI-Test 8289
bash ~/ComfyUI-MultiTenant/start_vanilla.sh /Users/comfyui/ComfyUI-Test 8289
```

---

## 同一安装内临时切原版（Bypass）

不想开第二套时，给多租户版设环境变量即可绕过全部多租户逻辑：

```bash
cd ~/ComfyUI-MultiTenant
MT_BYPASS=1 bash setup.sh     # 原版模式，端口 8188
bash setup.sh                 # 恢复多租户模式
```

---

## 保活（自动重启）

推荐 launchd：

```bash
cp ~/ComfyUI-MultiTenant/com.comfyui.multitenant.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.comfyui.multitenant.plist
```

日志：`service.out.log` / `service.err.log`（多租户目录内）。
详细说明见 `DEPLOY_KEEPALIVE.md`。

轻量 watchdog（不开机自启）：

```bash
cd ~/ComfyUI-MultiTenant
nohup bash watchdog.sh > /dev/null 2>&1 &
```

---

## 模型共享

原版测试版默认用自己的空 `models/`。想直接复用多租户的模型，在
`~/ComfyUI-Vanilla/user/extra_model_paths.yaml` 写：

```yaml
multitenant_models:
  base_path: /Users/comfyui/ComfyUI-MultiTenant/models
  checkpoints: checkpoints
  loras: loras
  vae: vae
  controlnet: controlnet
  clip: clip
```

然后重启原版实例。

---

## 端口速查

| 端口 | 服务 |
|---|---|
| 8188 | 多租户版（正式） |
| 8189 | 原版测试版 |
