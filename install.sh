#!/usr/bin/env bash
#
# app2nix-install.sh - One-line installer for app2nix
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash
#
# Options:
#   --docker       Install and run with Docker
#   --system       System-wide installation (requires root)
#   --user         User installation (home directory)
#   --upgrade      Upgrade existing installation
#   --uninstall    Remove installation
#   --help         Show this help
#
# Examples:
#   curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash
#   curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash -s -- --docker
#   curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash -s -- --upgrade
#

set -e

VERSION="3.1.0"
REPO="HiTechTN/app2nix"
RAW_URL="https://raw.githubusercontent.com/${REPO}/master"
INSTALL_DIR="${APP2NIX_DIR:-$HOME/.local/app2nix}"
if [ "$(id -u)" = "0" ]; then
    BIN_DIR="/usr/local/bin"
else
    BIN_DIR="${APP2NIX_BIN:-$HOME/.local/bin}"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[app2nix]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

find_python() {
    for cmd in python3 python python3.11 python3.10 python3.9; do
        if command -v "$cmd" >/dev/null 2>&1; then
            echo "$cmd"
            return 0
        fi
    done
    return 1
}

print_banner() {
    cat << 'BANNER'
                ___      _
 __ _ _ __ _ __|_  )_ _(_)_ __
/ _` | '_ \ '_ \/ /| ' \| \ \ /
\__,_| .__/ .__/___|_||_|_/_\_\
     |_|  |_|

    app2nix vVERSION_PLACEHOLDER
BANNER
}

show_help() {
    print_banner | sed "s/VERSION_PLACEHOLDER/$VERSION/g"
    cat << 'HELP'

USAGE:
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash [OPTIONS]

OPTIONS:
    --docker      Install and run using Docker (recommended)
    --system      System-wide installation (requires root)
    --user        User installation in ~/.local (default)
    --upgrade     Upgrade existing installation
    --uninstall   Remove app2nix installation
    --start       Start the app2nix server
    --stop        Stop the app2nix server
    --restart     Restart the app2nix server
    --logs        Show server logs
    --help        Show this help message

EXAMPLES:
    # Quick start with Docker (recommended)
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash -s --docker

    # User installation
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash

    # System installation
    sudo curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash -s --system

    # Upgrade existing installation
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash -s --upgrade

DOCKER COMMANDS:
    # Start server
    app2nix --start

    # View logs
    app2nix --logs

    # Stop server
    app2nix --stop

    # Open browser
    xdg-open http://localhost:8000

DOCUMENTATION:
    Web UI:     http://localhost:8000
    GitHub:     https://github.com/HiTechTN/app2nix
    Issues:     https://github.com/HiTechTN/app2nix/issues

HELP
}

check_docker() {
    if command -v docker >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

is_nixos() {
    grep -qi '^ID=nixos\|^ID=glfos' /etc/os-release 2>/dev/null ||
    test -f /etc/NIXOS ||
    command -v nixos-rebuild >/dev/null 2>&1
}

install_nixos() {
    log "NixOS detected — installing via nix profile..."
    mkdir -p "$BIN_DIR"
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"

    if command -v git >/dev/null 2>&1; then
        if [ -d .git ]; then
            log "Existing installation found — updating..."
            git fetch origin -q
            git checkout -f -B master origin/master -q
        else
            git clone --depth=1 https://github.com/${REPO}.git . 2>/dev/null || {
                git init -q
                git remote add origin https://github.com/${REPO}.git
                git fetch origin -q --depth=1
                git checkout -f -B master origin/master -q
            }
        fi
    else
        local tmpdir; tmpdir=$(mktemp -d)
        curl -sL "https://github.com/${REPO}/archive/refs/heads/master.tar.gz" | tar xz -C "$tmpdir"
        cp -r "$tmpdir"/app2nix-*/* "$INSTALL_DIR/"
        cp -r "$tmpdir"/app2nix-*/.[!.]* "$INSTALL_DIR/" 2>/dev/null || true
        rm -rf "$tmpdir"
    fi

    if nix profile list 2>/dev/null | grep -q app2nix; then
        nix profile remove app2nix 2>/dev/null || true
        nix profile remove app2nix-gui 2>/dev/null || true
    fi
    nix profile install "path:${INSTALL_DIR}#app2nix-gui" 2>/dev/null || \
    nix profile install "github:${REPO}#app2nix-gui" 2>/dev/null || {
        warn "Could not install via nix profile. Falling back to Python installation."
        install_user
        return
    }

    ok "NixOS installation complete!"
    echo
    info "app2nix is now available in your PATH"
    info "Run: app2nix --help"
}

install_docker() {
    log "Installing app2nix with Docker..."

    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"

    curl -sL "${RAW_URL}/Dockerfile" -o Dockerfile
    curl -sL "${RAW_URL}/docker-compose.yml" -o docker-compose.yml
    curl -sL "${RAW_URL}/requirements.txt" -o requirements.txt

    docker build -t hitechtn/app2nix:latest .

    docker compose up -d

    create_alias

    ok "Docker installation complete!"
    echo
    info "Server running at: http://localhost:8000"
    info "Docker container: app2nix"
    echo
    echo "Commands:"
    echo "  app2nix          # CLI tool (analyze packages)"
    echo "  app2nix start    # Start server"
    echo "  app2nix stop     # Stop server"
    echo "  app2nix restart  # Restart server"
    echo "  app2nix logs     # View logs"
}

start_docker() {
    cd "$INSTALL_DIR"
    if [ -f docker-compose.yml ]; then
        docker compose up -d
        ok "Server started"
    else
        error "Docker not installed. Run: curl -sL ... | bash -s --docker"
    fi
}

stop_docker() {
    cd "$INSTALL_DIR" 2>/dev/null || true
    if [ -f docker-compose.yml ]; then
        docker compose down 2>/dev/null && ok "Server stopped" || warn "Server was not running"
    fi
}

restart_docker() {
    stop_docker
    sleep 1
    start_docker
}

logs_docker() {
    cd "$INSTALL_DIR" 2>/dev/null || true
    if [ -f docker-compose.yml ]; then
        docker compose logs -f
    fi
}

install_system() {
    local os
    os=$(uname -s)

    log "System-wide installation (requires root)..."

    if [ "$os" = "Linux" ]; then
        apt-get update -qq
        apt-get install -y -qq python3 python3-venv git curl dpkg patchelf file 2>/dev/null || \
        pacman -S --noconfirm python python-pip git curl dpkg patchelf file 2>/dev/null || \
        dnf install -y python3 python3-pip git curl dpkg patchelf file 2>/dev/null
    fi

    install_user
    ok "System installation complete!"
    echo
    info "Commands installed to: /usr/local/bin/app2nix"
}

install_user() {
    log "Installing app2nix to $INSTALL_DIR..."

    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"

    cd "$INSTALL_DIR"

    if command -v git >/dev/null 2>&1; then
        if [ -d .git ]; then
            log "Existing installation found — updating..."
            git fetch origin -q
            git checkout -f -B master origin/master -q
        else
            rm -rf .git 2>/dev/null; rm -f .git 2>/dev/null
            git clone --depth=1 https://github.com/${REPO}.git . 2>/dev/null || {
                git init -q
                git remote add origin https://github.com/${REPO}.git
                git fetch origin -q --depth=1
                git checkout -f -B master origin/master -q
            }
        fi
    else
        local tmpdir; tmpdir=$(mktemp -d)
        curl -sL "https://github.com/${REPO}/archive/refs/heads/master.tar.gz" | tar xz -C "$tmpdir"
        cp -r "$tmpdir"/app2nix-*/* "$INSTALL_DIR/"
        cp -r "$tmpdir"/app2nix-*/.[!.]* "$INSTALL_DIR/" 2>/dev/null || true
        rm -rf "$tmpdir"
    fi

    local PYTHON
    PYTHON=$(find_python) || {
        error "Python not found. Install Python 3 first."
        exit 1
    }
    log "Using Python: $PYTHON"
    
    $PYTHON -m venv .venv 2>/dev/null || $PYTHON -m venv --system-site-packages .venv

    # Remove stale files from old installations that shadow the package
    rm -rf "$INSTALL_DIR/app2nix" 2>/dev/null || true

    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -e '.[gui]' -q 2>/dev/null || .venv/bin/pip install -r requirements.txt -q

    if [ ! -f .env ]; then
        local secret_key; secret_key=$($PYTHON -c "import secrets; print(secrets.token_hex(32))")
        cat > .env << ENVFILE
APP2NIX_SECRET_KEY=$secret_key
APP2NIX_DEBUG=false
APP2NIX_MAX_UPLOAD_SIZE=524288000
APP2NIX_VALIDATE_NIX=true
ENVFILE
        ok "Created .env with generated secret key"
    fi

    create_alias

    ok "User installation complete!"
    echo
    info "Server: app2nix-server"
    info "CLI:    app2nix"
    info "GUI:    app2nix-gui"
}

create_alias() {
    mkdir -p "$BIN_DIR"

    cat > "$BIN_DIR/app2nix" << ALIAS
#!/usr/bin/env bash
# app2nix - Universal Package to NixOS Converter
INSTALL_DIR="\$HOME/.local/app2nix"
PYTHON_VENV="\$INSTALL_DIR/.venv/bin/python"
start_server() {
    if command -v docker >/dev/null 2>&1 && [ -f "\$INSTALL_DIR/docker-compose.yml" ]; then
        cd "\$INSTALL_DIR" && docker compose up -d
    elif [ -f "\$PYTHON_VENV" ]; then
        cd "\$INSTALL_DIR" && nohup "\$PYTHON_VENV" -m app2nix serve >/dev/null 2>&1 &
    else
        echo "Error: no Docker or Python venv found" >&2
        exit 1
    fi
}
stop_server() {
    if command -v docker >/dev/null 2>&1 && docker ps -q --filter name=app2nix 2>/dev/null | grep -q .; then
        cd "\$INSTALL_DIR" 2>/dev/null && docker compose down
    else
        pkill -f "app2nix.*serve" 2>/dev/null || true
        pkill -f "uvicorn.*app2nix" 2>/dev/null || true
    fi
}
case "\${1:-}" in
    start) start_server ;;
    stop) stop_server ;;
    logs)
        if command -v docker >/dev/null 2>&1 && [ -f "\$INSTALL_DIR/docker-compose.yml" ]; then
            cd "\$INSTALL_DIR" && docker compose logs -f
        else
            echo "Error: logs only available in Docker mode" >&2
            exit 1
        fi
        ;;
    restart)
        stop_server; sleep 1; start_server
        ;;
    *)
        cd "\$INSTALL_DIR"
        if [ -f "\$PYTHON_VENV" ]; then
            exec "\$PYTHON_VENV" -m app2nix "\$@"
        else
            echo "Error: Python venv not found at \$INSTALL_DIR" >&2
            exit 1
        fi
        ;;
esac
ALIAS
    chmod +x "$BIN_DIR/app2nix"

    cat > "$BIN_DIR/app2nix-server" << SERVER
#!/usr/bin/env bash
# app2nix-server - Web UI for app2nix
INSTALL_DIR="\$HOME/.local/app2nix"
PYTHON_VENV="\$INSTALL_DIR/.venv/bin/python"
if [ -f "\$PYTHON_VENV" ]; then
    exec "\$PYTHON_VENV" -m app2nix serve "\$@"
else
    echo "Error: Python venv not found at \$INSTALL_DIR" >&2
    exit 1
fi
SERVER
    chmod +x "$BIN_DIR/app2nix-server"

    # Create launch_gui.py for NixOS compatibility
    cat > "$INSTALL_DIR/launch_gui.py" << 'LAUNCHGUI'
#!/usr/bin/env python3
"""Launcher for app2nix GUI on NixOS — adds source to path before importing."""
import sys
from pathlib import Path

src = Path(__file__).resolve().parent / "src"
if src.is_dir():
    sys.path.insert(0, str(src))

from app2nix.gui import run_gui

run_gui()
LAUNCHGUI

    cat > "$BIN_DIR/app2nix-gui" << 'GUIWRAP'
#!/usr/bin/env bash
# app2nix-gui - Graphical interface for app2nix
INSTALL_DIR="$HOME/.local/app2nix"
if [ ! -f "$INSTALL_DIR/launch_gui.py" ]; then
    echo "Error: app2nix not found at $INSTALL_DIR" >&2
    exit 1
fi
# On NixOS, PyQt6 from pip lacks patched shared libraries — use nix-shell
if command -v nix-shell >/dev/null 2>&1 && grep -qi '^ID=nixos' /etc/os-release 2>/dev/null; then
    exec nix-shell -p python3Packages.pyqt6 python3Packages.starlette python3Packages.uvicorn \
         python3Packages.python-multipart python3Packages.httpx python3Packages.pydantic \
         python3Packages.pydantic-settings python3Packages.jinja2 python3Packages.typer \
         python3Packages.rich python3Packages.itsdangerous stdenv.cc.cc.lib \
         --run "unset QT_PLUGIN_PATH; export QT_LOGGING_RULES='*.debug=false;qt.*.debug=false'; exec python3 $INSTALL_DIR/launch_gui.py $*"
else
    exec "$INSTALL_DIR/.venv/bin/python" -m app2nix gui "$@"
fi
GUIWRAP
    chmod +x "$BIN_DIR/app2nix-gui"
}

uninstall() {
    warn "Uninstalling app2nix..."

    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_DIR/app2nix"
    rm -f "$BIN_DIR/app2nix-server"
    rm -f "$BIN_DIR/app2nix-gui"

    docker stop app2nix 2>/dev/null || true
    docker rm app2nix 2>/dev/null || true

    ok "Uninstalled!"
}

upgrade() {
    if check_docker; then
        cd "$INSTALL_DIR" 2>/dev/null && docker compose pull && docker compose up -d --force-recreate
    else
        cd "$INSTALL_DIR"
        git fetch origin -q
        git checkout -f -B master origin/master -q
        .venv/bin/pip install -e '.[gui]' -q 2>/dev/null || .venv/bin/pip install -r requirements.txt -q
        if [ ! -f .env ]; then
            local secret_key; secret_key=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "$(date +%s%N | sha256sum | head -c64)")
            cat > .env << ENVFILE
APP2NIX_SECRET_KEY=$secret_key
APP2NIX_DEBUG=false
APP2NIX_MAX_UPLOAD_SIZE=524288000
APP2NIX_VALIDATE_NIX=true
ENVFILE
            ok "Created .env with generated secret key"
        fi
        create_alias
    fi
    ok "Upgraded to latest version!"
}

main() {
    local arg="${1:-}"

    case "$arg" in
        docker)
            check_docker && install_docker || { error "Docker not found. Install Docker first."; exit 1; }
            ;;
        system)
            [ "$(id -u)" = "0" ] && install_system || { error "System installation requires root"; exit 1; }
            ;;
        user|u)
            install_user
            ;;
        upgrade|update)
            upgrade
            ;;
        uninstall|remove)
            uninstall
            ;;
        start)
            if check_docker; then
                start_docker
            else
                cd "$INSTALL_DIR" 2>/dev/null && .venv/bin/python -m app2nix serve &>/dev/null &
                ok "Server started at http://localhost:8000"
            fi
            ;;
        stop)
            if check_docker; then
                stop_docker
            else
                pkill -f "app2nix.*serve" 2>/dev/null
                ok "Server stopped"
            fi
            ;;
        restart)
            if check_docker; then
                stop_docker
                sleep 1
                start_docker
            else
                pkill -f "app2nix.*serve" 2>/dev/null
                sleep 1
                cd "$INSTALL_DIR" 2>/dev/null && .venv/bin/python -m app2nix serve &>/dev/null &
                ok "Server restarted at http://localhost:8000"
            fi
            ;;
        logs|l)
            if check_docker; then
                logs_docker
            else
                journalctl -u app2nix 2>/dev/null || docker logs app2nix 2>/dev/null
            fi
            ;;
        nixos|nix)
            install_nixos
            ;;
        help|-h|--help)
            show_help
            ;;
        "")
            print_banner | sed "s/VERSION_PLACEHOLDER/$VERSION/g"
            echo
            if is_nixos; then
                log "NixOS/GLF-OS detected — installing natively"
                install_nixos
            elif check_docker; then
                install_docker
            else
                install_user
            fi
            ;;
        *)
            error "Unknown option: $arg"
            echo "Use: curl ... | bash docker|nixos|system|user|upgrade|uninstall|start|stop|restart|logs|help"
            exit 1
            ;;
    esac
}

main "$@"