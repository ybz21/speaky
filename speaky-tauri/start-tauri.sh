#!/bin/bash

# Speaky Tauri 开发环境启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查命令是否存在
check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# 加载 nvm 环境
load_nvm() {
    if [ -f "$HOME/.nvm/nvm.sh" ]; then
        source "$HOME/.nvm/nvm.sh"
    fi
}

# 加载 Rust 环境
load_cargo() {
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi
}

# 检查 Rust 环境
check_rust() {
    log_info "检查 Rust 环境..."
    load_cargo
    if check_command rustc; then
        local version=$(rustc --version)
        log_success "Rust 已安装: $version"
        return 0
    else
        log_error "Rust 未安装"
        echo ""
        echo "请运行以下命令安装 Rust:"
        echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        echo "  source ~/.cargo/env"
        echo ""
        return 1
    fi
}

# 检查 Node.js 环境和版本
check_node() {
    log_info "检查 Node.js 环境..."
    load_nvm
    if check_command node; then
        local version=$(node --version | sed 's/v//')
        local major=$(echo "$version" | cut -d. -f1)
        local minor=$(echo "$version" | cut -d. -f2)

        # 需要 Node.js 20.19+ 或 22.12+
        local version_ok=false
        if [ "$major" -ge 24 ]; then
            version_ok=true
        elif [ "$major" -eq 22 ] && [ "$minor" -ge 12 ]; then
            version_ok=true
        elif [ "$major" -eq 20 ] && [ "$minor" -ge 19 ]; then
            version_ok=true
        fi

        if [ "$version_ok" = true ]; then
            log_success "Node.js 已安装: v$version"
            return 0
        else
            log_warn "Node.js 版本过低: v$version (需要 20.19+ 或 22.12+)"
            echo ""
            echo "请升级 Node.js:"
            echo "  nvm install 22"
            echo "  nvm use 22"
            echo ""

            # 尝试自动升级
            if check_command nvm; then
                read -p "是否自动升级到 Node.js 22? [y/N] " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    nvm install 22
                    nvm use 22
                    return 0
                fi
            fi
            return 1
        fi
    else
        log_error "Node.js 未安装"
        echo ""
        echo "请安装 Node.js 20.19+ (推荐使用 nvm):"
        echo "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
        echo "  source ~/.nvm/nvm.sh"
        echo "  nvm install 22"
        echo ""
        return 1
    fi
}

# 检查 Linux 系统依赖
check_linux_deps() {
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        return 0
    fi

    log_info "检查 Linux 系统依赖..."

    local missing_deps=()

    # 检查 webkit2gtk
    if ! pkg-config --exists webkit2gtk-4.1 2>/dev/null; then
        missing_deps+=("libwebkit2gtk-4.1-dev")
    fi

    # 检查 appindicator (支持 ayatana 替代版本)
    if ! pkg-config --exists appindicator3-0.1 2>/dev/null && ! pkg-config --exists ayatana-appindicator3-0.1 2>/dev/null; then
        missing_deps+=("libayatana-appindicator3-dev")
    fi

    # 检查 alsa (音频)
    if ! pkg-config --exists alsa 2>/dev/null; then
        missing_deps+=("libasound2-dev")
    fi

    # 检查 openssl
    if ! pkg-config --exists openssl 2>/dev/null; then
        missing_deps+=("libssl-dev")
    fi

    # 检查 glib-2.0
    if ! pkg-config --exists glib-2.0 2>/dev/null; then
        missing_deps+=("libglib2.0-dev")
    fi

    # 检查 gtk-3.0
    if ! pkg-config --exists gtk+-3.0 2>/dev/null; then
        missing_deps+=("libgtk-3-dev")
    fi

    # 检查 soup-3.0
    if ! pkg-config --exists libsoup-3.0 2>/dev/null; then
        missing_deps+=("libsoup-3.0-dev")
    fi

    # 检查 javascriptcoregtk-4.1
    if ! pkg-config --exists javascriptcoregtk-4.1 2>/dev/null; then
        missing_deps+=("libjavascriptcoregtk-4.1-dev")
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_warn "缺少以下系统依赖: ${missing_deps[*]}"
        echo ""
        echo "请运行以下命令安装:"
        echo "  sudo apt install -y ${missing_deps[*]} librsvg2-dev patchelf"
        echo ""
        read -p "是否现在安装? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo apt install -y ${missing_deps[*]} librsvg2-dev patchelf
        else
            return 1
        fi
    else
        log_success "Linux 系统依赖已满足"
    fi

    return 0
}

# 检查 npm 依赖
check_npm_deps() {
    log_info "检查 npm 依赖..."
    if [ ! -d "node_modules" ]; then
        log_warn "node_modules 不存在，正在安装依赖..."
        npm install
    else
        log_success "npm 依赖已安装"
    fi
}

# 检查 Tauri CLI
check_tauri_cli() {
    log_info "检查 Tauri CLI..."
    if npm list @tauri-apps/cli &>/dev/null; then
        log_success "Tauri CLI 已安装"
    else
        log_warn "Tauri CLI 未安装，正在安装..."
        npm install -D @tauri-apps/cli
    fi
}

# 主函数
main() {
    echo ""
    echo "=========================================="
    echo "       Speaky Tauri 开发环境启动"
    echo "=========================================="
    echo ""

    # 加载环境
    load_nvm
    load_cargo

    # 环境检查
    local checks_passed=true

    check_rust || checks_passed=false
    check_node || checks_passed=false
    check_linux_deps || checks_passed=false

    if [ "$checks_passed" = false ]; then
        log_error "环境检查失败，请安装缺失的依赖后重试"
        exit 1
    fi

    check_npm_deps
    check_tauri_cli

    echo ""
    log_success "环境检查通过!"
    echo ""

    # 解析参数
    case "${1:-dev}" in
        dev)
            log_info "启动开发服务器..."
            echo ""
            npm run tauri dev
            ;;
        build)
            log_info "构建生产版本..."
            echo ""
            npm run tauri build
            ;;
        frontend)
            log_info "仅启动前端开发服务器..."
            echo ""
            npm run dev
            ;;
        *)
            echo "用法: $0 [dev|build|frontend]"
            echo ""
            echo "  dev      - 启动 Tauri 开发模式 (默认)"
            echo "  build    - 构建生产版本"
            echo "  frontend - 仅启动前端开发服务器"
            exit 1
            ;;
    esac
}

main "$@"
