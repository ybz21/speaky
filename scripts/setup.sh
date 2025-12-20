#!/usr/bin/env bash
# Full setup script for Speaky
# This script installs all dependencies including MCP servers

set -e

# Get script directory (works in bash)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "Speaky Setup"
echo "========================================="
echo "Project directory: $PROJECT_DIR"

# 1. Check Python version
echo ""
echo "[1/4] Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]; }; then
    echo "Warning: Python 3.12+ is recommended (found: $PYTHON_VERSION)"
fi
echo "Python $PYTHON_VERSION - OK"

# 2. Install Python dependencies
echo ""
echo "[2/4] Installing Python dependencies..."
cd "$PROJECT_DIR"

if command -v uv > /dev/null 2>&1; then
    echo "Using uv for installation..."
    uv sync
else
    echo "Using pip for installation..."
    python3 -m pip install -e .
fi

# 3. Install MCP dependencies
echo ""
echo "[3/4] Installing MCP dependencies..."
bash "$SCRIPT_DIR/install_mcp.sh"

# 4. Check configuration
echo ""
echo "[4/4] Checking configuration..."
CONFIG_DIR="${HOME}/.speaky"

mkdir -p "$CONFIG_DIR"

# Copy mcp.yaml to config directory
echo "Copying MCP config..."
cp "$PROJECT_DIR/mcp.yaml" "${CONFIG_DIR}/mcp.yaml"

echo ""
echo "========================================="
echo "Setup complete!"
echo "========================================="
echo ""
echo "To start Speaky, run:"
echo "  speaky"
echo ""
echo "Or for development:"
echo "  uv run speaky"
echo ""
