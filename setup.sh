#!/bin/bash
# ComfyUI-MultiTenant startup script for Mac

set -e

cd "$(dirname "$0")"

echo "=== ComfyUI-MultiTenant Setup ==="

# Check Python
PYTHON=$(which python3.11 2>/dev/null || which python3 2>/dev/null)
if [ -z "$PYTHON" ]; then
    echo "Error: Python not found. Install via: brew install python@3.11"
    exit 1
fi

echo "Using: $($PYTHON --version)"

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

source venv/bin/activate
PYTHON=venv/bin/python3

# Install dependencies
echo "Installing requirements..."
$PYTHON -m pip install --upgrade pip -q
$PYTHON -m pip install -r requirements.txt -q 2>/dev/null

# Install ComfyUI-Manager deps
if [ -f custom_nodes/ComfyUI-Manager/requirements.txt ]; then
    $PYTHON -m pip install -r custom_nodes/ComfyUI-Manager/requirements.txt -q 2>/dev/null || true
fi

echo "=== Starting ComfyUI-MultiTenant ==="
echo "Open http://<this-mac-ip>:8188 or http://127.0.0.1:8188 and login with admin / admin123"
echo ""
$PYTHON main.py --listen 0.0.0.0 "$@"
