# 保活部署

两种方式二选一，推荐 launchd（系统级、开机自启、崩溃自愈）。

## 方式一：launchd（推荐）

```bash
cd /Users/comfyui/ComfyUI-MultiTenant
cp com.comfyui.multitenant.plist ~/Library/LaunchAgents/

# 启动服务
launchctl load ~/Library/LaunchAgents/com.comfyui.multitenant.plist

# 查看状态
launchctl list | grep comfyui

# 查看日志
tail -f service.out.log service.err.log

# 停止服务
launchctl unload ~/Library/LaunchAgents/com.comfyui.multitenant.plist
```

- 开机/登录自动启动
- 崩溃自动拉起（KeepAlive）
- 退出码 0 时不会重启（防止正常退出后死循环）

## 方式二：watchdog 脚本（轻量）

```bash
cd /Users/comfyui/ComfyUI-MultiTenant
nohup bash watchdog.sh > /dev/null 2>&1 &
```

每 15 秒探测 `http://127.0.0.1:8188/api/health`，无响应就杀掉旧进程并重启。
日志写入 `watchdog.log`。

注意：watchdog 不是开机自启，重启机器后需要手动再跑一次；也可以把
`watchdog.sh` 加到 cron / launchd 里配合使用。
