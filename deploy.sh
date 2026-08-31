#!/bin/bash
# ComfyUI-MT Plugin Deployment Script
# Deploys the plugin to a ComfyUI installation without modifying core code

set -e

PLUGIN_NAME="comfyui_mt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default ComfyUI installation path
COMFYUI_DIR="${1:-$HOME/ComfyUI}"

echo "=== ComfyUI-MT Plugin Deployment ==="
echo "Plugin source: $SCRIPT_DIR"
echo "ComfyUI target: $COMFYUI_DIR"

# Check if ComfyUI exists
if [ ! -d "$COMFYUI_DIR" ]; then
    echo "Error: ComfyUI not found at $COMFYUI_DIR"
    echo "Usage: $0 [path-to-comfyui]"
    exit 1
fi

if [ ! -f "$COMFYUI_DIR/main.py" ]; then
    echo "Error: $COMFYUI_DIR does not appear to be a ComfyUI installation"
    exit 1
fi

# Create custom_nodes directory if needed
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"
mkdir -p "$CUSTOM_NODES_DIR"

# Remove old version if exists
TARGET_DIR="$CUSTOM_NODES_DIR/$PLUGIN_NAME"
if [ -d "$TARGET_DIR" ]; then
    echo "Removing old version..."
    rm -rf "$TARGET_DIR"
fi

# Copy plugin
echo "Installing plugin..."
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR"/*.py "$TARGET_DIR/"
cp -r "$SCRIPT_DIR/web" "$TARGET_DIR/"

# Create __init__.py if not exists (for Python package)
if [ ! -f "$TARGET_DIR/__init__.py" ]; then
    echo '"""ComfyUI Multi-Tenant Plugin"""' > "$TARGET_DIR/__init__.py"
fi

echo ""
echo "=== Deployment Complete ==="
echo "Plugin installed to: $TARGET_DIR"
echo ""
echo "To activate:"
echo "  1. Restart ComfyUI"
echo "  2. Access http://localhost:8188"
echo "  3. Login with admin / admin123"
echo ""
echo "To uninstall:"
echo "  rm -rf $TARGET_DIR"
echo ""
