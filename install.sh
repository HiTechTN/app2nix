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

VERSION="1.0.0"
REPO="HiTechTN/app2nix"
RAW_URL="https://raw.githubusercontent.com/${REPO}/master"
INSTALL_DIR="${APP2NIX_DIR:-$HOME/.local/app2nix}"
BIN_DIR="${APP2NIX_BIN:-$HOME/.local/bin}"

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

print_banner() {
    cat << 'BANNER'
     _      ____           _           _
    | |    |  _ \         | |         | |
    | |    | |_) | ___ _ _| |_ ___ _ __| | ___  ___
    | |    | _ < / _ \ '__| __/ _ \ '__| |/ _ \/ __|
    | |____| |_) |  __/ |  | ||  __/ |  | |  __/\__ \
    |______|____/ \___|_|   \__\___|_|  |_|\___||___/

    Universal Package to NixOS Converter vVERSION_PLACEHOLDER
BANNER
}

show_help() {
    print_banner | sed "s/VERSION_PLACEHOLDER/$VERSION/g"
    cat << 'HELP'

USAGE:
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash [OPTIONS]

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
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash -s --docker

    # User installation
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash

    # System installation
    sudo curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash -s --system

    # Upgrade existing installation
    curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash -s --upgrade

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
        git clone --depth=1 https://github.com/${REPO}.git . 2>/dev/null || {
            rm -rf .git
            git init -q
            git remote add origin https://github.com/${REPO}.git
            git fetch origin -q
            git checkout -b master origin/master -q
        }
    else
        curl -sL "https://github.com/${REPO}/archive/refs/heads/master.tar.gz" | tar xz
        mv app2nix-*/* .
        rm -rf app2nix-*
    fi

    python3 -m venv .venv 2>/dev/null || python3 -m venv --system-site-packages .venv
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -e . -q 2>/dev/null || .venv/bin/pip install -r requirements.txt -q

    create_alias

    ok "User installation complete!"
    echo
    info "Server: app2nix-server"
    info "CLI:    app2nix"
}

create_alias() {
    cat > "$BIN_DIR/app2nix" << 'ALIAS'
#!/usr/bin/env bash
# app2nix - Universal Package to NixOS Converter
INSTALL_DIR="$HOME/.local/app2nix"
case "${1:-}" in
    start)
        cd "$INSTALL_DIR" && docker compose up -d
        ;;
    stop)
        cd "$INSTALL_DIR" && docker compose down
        ;;
    logs)
        cd "$INSTALL_DIR" && docker compose logs -f
        ;;
    restart)
        cd "$INSTALL_DIR" && docker compose restart
        ;;
    *)
        cd "$INSTALL_DIR"
        if [ -f .venv/bin/python ]; then
            exec .venv/bin/python "$INSTALL_DIR/main.py" "$@"
        else
            exec python3 "$INSTALL_DIR/main.py" "$@"
        fi
        ;;
esac
ALIAS
    chmod +x "$BIN_DIR/app2nix"

    cat > "$BIN_DIR/app2nix-server" << 'SERVER'
#!/usr/bin/env bash
# app2nix-server - Web UI for app2nix
INSTALL_DIR="$HOME/.local/app2nix"
cd "$INSTALL_DIR"
if [ -f .venv/bin/python ]; then
    exec .venv/bin/python "$INSTALL_DIR/server.py" "$@"
else
    exec python3 "$INSTALL_DIR/server.py" "$@"
fi
SERVER
    chmod +x "$BIN_DIR/app2nix-server"
}

uninstall() {
    warn "Uninstalling app2nix..."

    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_DIR/app2nix"
    rm -f "$BIN_DIR/app2nix-server"

    docker stop app2nix 2>/dev/null || true
    docker rm app2nix 2>/dev/null || true

    ok "Uninstalled!"
}

upgrade() {
    if check_docker; then
        cd "$INSTALL_DIR" 2>/dev/null && docker compose pull && docker compose up -d --force-recreate
    else
        cd "$INSTALL_DIR"
        git pull origin master 2>/dev/null || {
            rm -rf .git
            git init -q
            git remote add origin https://github.com/${REPO}.git
            git pull origin master
        }
        .venv/bin/pip install -e . -q 2>/dev/null || .venv/bin/pip install -r requirements.txt -q
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
                cd "$INSTALL_DIR" 2>/dev/null && .venv/bin/python server.py &>/dev/null &
                ok "Server started at http://localhost:8000"
            fi
            ;;
        stop)
            if check_docker; then
                stop_docker
            else
                pkill -f "python.*server.py" 2>/dev/null
                ok "Server stopped"
            fi
            ;;
        restart)
            stop
            sleep 1
            start
            ;;
        logs|l)
            if check_docker; then
                logs_docker
            else
                journalctl -u app2nix 2>/dev/null || docker logs app2nix 2>/dev/null
            fi
            ;;
        help|-h|--help)
            show_help
            ;;
        "")
            print_banner | sed "s/VERSION_PLACEHOLDER/$VERSION/g"
            echo
            if check_docker; then
                install_docker
            else
                install_user
            fi
            ;;
        *)
            error "Unknown option: $arg"
            echo "Use: curl ... | bash docker|system|user|upgrade|uninstall|start|stop|restart|logs|help"
            exit 1
            ;;
    esac
}

main "$@"