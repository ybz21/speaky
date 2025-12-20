#!/usr/bin/env bash
# Install MCP server dependencies for Speaky
# This script pre-installs all required MCP packages

set -e

echo "Installing MCP server dependencies..."

MCP_DIR="${HOME}/.speaky/mcp"
mkdir -p "$MCP_DIR"

# ===== NPM Packages =====
# Check if npm is available
if ! command -v npm > /dev/null 2>&1; then
    echo "Error: npm is not installed. Please install Node.js first."
    echo "Visit: https://nodejs.org/"
    exit 1
fi

cd "$MCP_DIR"

# Initialize package.json if not exists
if [ ! -f "package.json" ]; then
    npm init -y > /dev/null 2>&1
fi

# Install MCP npm packages
echo ""
echo "[1/3] Installing @playwright/mcp..."
npm install @playwright/mcp@latest --save --silent

echo "[2/3] Installing @modelcontextprotocol/server-filesystem..."
npm install @modelcontextprotocol/server-filesystem --save --silent

# Install playwright browsers
echo "[3/3] Installing Playwright browsers..."
npx playwright install chromium

# ===== Python Packages (mcp-server-fetch) =====
echo ""
echo "[Optional] mcp-server-fetch is a Python package."
echo "To use it, run: uv tool install mcp-server-fetch"
echo "Or: pip install mcp-server-fetch"

echo ""
echo "========================================="
echo "MCP dependencies installed successfully!"
echo "========================================="
echo "Location: $MCP_DIR"
echo ""
echo "Installed servers:"
echo "  - @playwright/mcp (browser automation)"
echo "  - @modelcontextprotocol/server-filesystem (file operations)"
echo ""
