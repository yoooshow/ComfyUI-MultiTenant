# 双 ComfyUI 实例

一台机器同时跑两个 ComfyUI：

| 实例 | 端口 | 模式 | 用户目录 |
|---|---|---|---|
| 多租户 | 8188 | 登录/计费/顶栏 | `user/`（默认） |
| 原版 | 8189 | `MT_BYPASS=1` 纯原版 | `user_vanilla/` |

两个实例**共享** `models/` 和 `custom_nodes/`，避免重复下载模型；
**分开** user 目录与数据库，互不干扰。

## 一键启动

```bash
cd /Users/comfyui/ComfyUI-MultiTenant
bash start_dual.sh
```

- 多租户：`http://<本机IP>:8188`
- 原版：`http://<本机IP>:8189`

## 手动启动

```bash
cd /Users/comfyui/ComfyUI-MultiTenant

# 原版（8189）
MT_BYPASS=1 venv/bin/python3 main.py --listen 0.0.0.0 --port 8189 --enable-manager \
  --user-directory "$(pwd)/user_vanilla"

# 多租户（8188）
venv/bin/python3 main.py --listen 0.0.0.0 --port 8188 --enable-manager
```

## 停止

```bash
kill $(pgrep -f "port 8188") $(pgrep -f "port 8189")
```

## launchd 保活双实例

复制 plist 为两份，分别改 `ProgramArguments` 里的端口与
`EnvironmentVariables`（原版实例加 `MT_BYPASS=1`），
`StandardOutPath/StandardErrorPath` 也分开，然后分别 load。

## 注意

同一台 Mac 两个实例共享 8GB 内存，**不要同时跑大任务**。
原版实例主要给管理员调试/装节点用。
