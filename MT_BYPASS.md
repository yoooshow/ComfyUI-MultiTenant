# 多租户 Bypass 模式

设 `MT_BYPASS=1` 时，ComfyUI 以**纯原版模式**运行：
- 不加载登录页、顶栏、计费、工作流选择器
- 不注入任何脚本，完整保留 ComfyUI 原生 UI 与 API
- 适合临时让用户直接用原版 ComfyUI

## 开启方式

```bash
cd /Users/comfyui/ComfyUI-MultiTenant
MT_BYPASS=1 bash setup.sh
```

或手动启动：

```bash
cd /Users/comfyui/ComfyUI-MultiTenant
MT_BYPASS=1 venv/bin/python3 main.py --listen 0.0.0.0 --enable-manager
```

## 关闭方式

不设置 `MT_BYPASS`（或设为 0/false）即恢复正常多租户模式：

```bash
cd /Users/comfyui/ComfyUI-MultiTenant
bash setup.sh
```

## launchd 模式

如果用 launchd 保活，编辑 `com.comfyui.multitenant.plist`，
在 `EnvironmentVariables` 里加：

```xml
<key>MT_BYPASS</key>
<string>1</string>
```

然后重新加载：

```bash
launchctl unload ~/Library/LaunchAgents/com.comfyui.multitenant.plist
launchctl load ~/Library/LaunchAgents/com.comfyui.multitenant.plist
```
