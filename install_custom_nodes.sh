#!/bin/bash
# 为原版 ComfyUI 安装所有 custom_nodes 的 Python 依赖
# 用法: bash install_custom_nodes.sh [原版目录]
set -e

VANILLA_DIR="${1:-$HOME/ComfyUI-Vanilla}"

if [ ! -d "$VANILLA_DIR/venv" ]; then
  echo "错误: $VANILLA_DIR/venv 不存在"
  exit 1
fi

cd "$VANILLA_DIR"
source venv/bin/activate

echo "=== 安装 custom_nodes 依赖 ==="
for d in custom_nodes/*/; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  if [ -f "$d/requirements.txt" ]; then
    echo ">>> $name"
    pip install -r "$d/requirements.txt" -q || echo "    安装失败: $name"
  else
    echo "--- $name (无 requirements.txt)"
  fi
done

echo ""
echo "=== 完成，请重启原版实例 ==="
