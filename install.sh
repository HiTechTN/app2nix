#!/usr/bin/env bash
#
# app2nix-installer.sh - Install app2nix on GLF-OS (NixOS)
# Usage: curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | sudo bash
#

VERSION="1.0.0"
REPO="HiTechTN/app2nix"
INSTALL_DIR="/opt/app2nix"
BIN_DIR="/usr/local/bin"

log_info() { echo "[INFO] $1"; }
log_success() { echo "[OK] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif [ -f /run/current-system/sw/etc/os-release ]; then
        echo "nixos"
    else
        echo "nixos"
    fi
}

install_dependencies() {
    local os
    os=$(detect_os)
    log_info "Detected OS: $os"
    
    case "$os" in
        nixos|glfos)
            log_info "Installing dependencies via Nix..."
            if command -v nix-env >/dev/null 2>&1; then
                nix-env -iA nixpkgs.dpkg nixpkgs.patchelf nixpkgs.file 2>/dev/null || true
                log_success "Done"
            else
                log_warn "Nix not found, skipping"
            fi
            ;;
        debian|ubuntu|linuxmint|pop|popos)
            log_info "Installing dependencies via apt..."
            apt-get update -qq
            apt-get install -y -qq dpkg patchelf file python3 git curl >/dev/null 2>&1
            log_success "Done"
            ;;
        *)
            log_warn "Unknown OS: $os"
            ;;
    esac
}

download_app2nix() {
    log_info "Downloading app2nix..."
    
    rm -rf "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    if command -v git >/dev/null 2>&1; then
        git init -q
        git remote add origin "https://github.com/${REPO}.git"
        git fetch origin -q
        git checkout -b master origin/master -q
    else
        curl -sL "https://github.com/${REPO}/archive/refs/heads/master.tar.gz" | tar xz
        mv app2nix-master/* .
        rm -rf app2nix-master
    fi
    
    log_success "Downloaded"
}

create_python_venv() {
    log_info "Setting up Python..."
    
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "Python3 not found"
        return 1
    fi
    
    cd "$INSTALL_DIR"
    python3 -m venv .venv
    .venv/bin/pip install -q fastapi uvicorn pydantic python-multipart
    
    log_success "Python ready"
}

create_system_service() {
    log_info "Creating systemd service..."
    
    cat > /etc/systemd/system/app2nix.service << ENDSERVICE
[Unit]
Description=app2nix - Universal package converter
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
ENDSERVICE
    
    systemctl daemon-reload -q
    systemctl enable app2nix.service -q
    
    log_success "Service created"
}

create_wrapper_scripts() {
    log_info "Creating commands..."
    
    mkdir -p "$BIN_DIR"
    
    echo "#!/bin/bash" > "$BIN_DIR/app2nix"
    echo "exec $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py \"\$@\"" >> "$BIN_DIR/app2nix"
    chmod +x "$BIN_DIR/app2nix"
    
    echo "#!/bin/bash" > "$BIN_DIR/app2nix-server"
    echo "exec $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/server.py \"\$@\"" >> "$BIN_DIR/app2nix-server"
    chmod +x "$BIN_DIR/app2nix-server"
    
    log_success "Commands created"
}

create_aliases() {
    log_info "Creating aliases..."
    
    echo "alias app2nix='$BIN_DIR/app2nix'" > /etc/profile.d/app2nix.sh
    echo "alias app2nix-server='$BIN_DIR/app2nix-server'" >> /etc/profile.d/app2nix.sh
    chmod +x /etc/profile.d/app2nix.sh
    
    log_success "Aliases created"
}

enable_autostart() {
    log_info "Starting service..."
    systemctl start app2nix.service -q 2>/dev/null || true
    log_success "Started"
}

print_summary() {
    echo
    echo "=========================================="
    echo "  app2nix v$VERSION installed!"
    echo "=========================================="
    echo
    echo "Web UI: http://localhost:8000"
    echo "CLI:  app2nix"
    echo
    echo "Commands:"
    echo "  app2nix <package.deb>"
    echo "  app2nix-server"
    echo "=========================================="
}

main() {
    echo "=========================================="
    echo "  app2nix Installer v$VERSION"
    echo "  For GLF-OS (NixOS)"
    echo "=========================================="
    
    check_root
    install_dependencies
    download_app2nix
    create_python_venv
    create_system_service
    create_wrapper_scripts
    create_aliases
    enable_autostart
    
    print_summary
}

main