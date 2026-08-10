# 独立原版 ComfyUI（测试实例）

与多租户完全隔离的第二个 ComfyUI，直接跟随官方仓库，可随时更新。

| 项目 | 多租户 | 原版测试 |
|---|---|---|
| 目录 | `~/ComfyUI-MultiTenant` | `~/ComfyUI-Vanilla` |
| 仓库 | 你的 fork（多租户） | 官方 comfyanonymous/ComfyUI |
| 端口 | 8188 | 8189 |
| venv | 独立 | 独立 |
| models/custom_nodes/user | 独立 | 独立 |

## 首次安装

```bash
cd /Users/comfyui
bash ~/ComfyUI-MultiTenant/install_vanilla.sh
```

默认装到 `/Users/comfyui/ComfyUI-Vanilla`、端口 8189。
需要换目录/端口：

```bash
bash ~/ComfyUI-MultiTenant/install_vanilla.sh /Users/comfyui/ComfyUI-Test 8289
```

## 实时更新（跟随官方最新版）

```bash
bash ~/ComfyUI-MultiTenant/update_vanilla.sh
```

脚本会：停掉 8189 实例 → `git pull` 官方仓库 → 更新依赖 → 重启。

## 共享模型（可选）

原版测试实例默认用自己的 `models/`。想直接复用多租户的模型，创建
`~/ComfyUI-Vanilla/user/extra_model_paths.yaml`：

```yaml
multitenant_models:
  base_path: /Users/comfyui/ComfyUI-MultiTenant/models
  checkpoints: checkpoints
  loras: loras
  vae: vae
  controlnet: controlnet
  clip: clip
```

重启原版实例即可看到多租户那边的模型，不占双份空间。

## 停止原版实例

```bash
pkill -f "port 8189"
```
