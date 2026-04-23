#!/usr/bin/env bash
#
# app2nix-installer.sh - Install app2nix on GLF-OS
# Usage: curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash
#

set -e

VERSION="1.0.0"
REPO="HiTechTN/app2nix"
INSTALL_DIR="/opt/app2nix"
BIN_DIR="/usr/local/bin"
DATA_DIR="/var/lib/app2nix"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_dependencies() {
    local missing=()
    local deps=("curl" "python3" "git" "dpkg-deb" "patchelf")
    
    for cmd in "${deps[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Missing dependencies: ${missing[*]}"
        log_info "Installing missing dependencies..."
        apt-get update && apt-get install -y "${missing[@]}"
    fi
}

download_app2nix() {
    log_info "Downloading app2nix v${VERSION}..."
    
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    if command -v git &> /dev/null; then
        git clone --depth 1 "https://github.com/${REPO}.git" .
    else
        curl -sL "https://github.com/${REPO}/archive/refs/heads/main.tar.gz" | tar xz
        mv app2nix-main/* .
        rm -rf app2nix-main
    fi
    
    log_success "Downloaded to $INSTALL_DIR"
}

create_system_service() {
    log_info "Creating system service..."
    
    cat > /etc/systemd/system/app2nix.service << EOF
[Unit]
Description=app2nix - Universal package converter
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable app2nix.service
    
    log_success "Service created"
}

create_desktop_entry() {
    log_info "Creating desktop entry..."
    
    mkdir -p /usr/share/applications
    cat > /usr/share/applications/app2nix.desktop << EOF
[Desktop Entry]
Name=app2nix
Comment=Convert packages to NixOS
Exec=$BIN_DIR/app2nix-gui
Icon=system-software-install
Type=Application
Categories=Development;System;
Keywords=nixos;package;converter;deb;rpm;appimage;
EOF
    
    update-desktop-database /usr/share/applications
    
    log_success "Desktop entry created"
}

create_shell_aliases() {
    log_info "Creating shell aliases..."
    
    cat > /etc/profile.d/app2nix.sh << EOF
# app2nix shell aliases
alias app2nix='python3 $INSTALL_DIR/main.py'
alias app2nix-server='python3 $INSTALL_DIR/server.py'
alias app2nix-analyze='python3 $INSTALL_DIR/universal_analyze.py'
EOF
    
    log_success "Aliases created"
}

setup_firewall() {
    if command -v ufw &> /dev/null; then
        log_info "Configuring firewall..."
        ufw allow 8000/tcp comment 'app2nix web UI'
        ufw reload
        log_success "Firewall configured"
    fi
}

setup_nix_channel() {
    log_info "Setting up Nix channels..."
    
    if command -v nix-channel &> /dev/null; then
        nix-channel --add https://nixos.org/channels/nixpkgs-unstable nixpkgs
        nix-channel --update
        log_success "Nix channels configured"
    else
        log_warn "Nix not installed, skipping channel setup"
    fi
}

enable_autostart() {
    log_info "Enabling autostart..."
    
    systemctl enable app2nix.service
    systemctl start app2nix.service
    
    log_success "Autostart enabled"
}

print_summary() {
    echo
    echo ========================================
    echo "  app2nix v${VERSION} installed successfully!"
    echo ========================================
    echo
    echo "Web UI:    http://localhost:8000"
    echo "Install:  $INSTALL_DIR"
    echo "Bin:       $BIN_DIR/app2nix"
    echo
    echo "Commands:"
    echo "  app2nix <package.deb>    # CLI"
    echo "  app2nix-server          # Web UI"
    echo "  app2nix-analyze        # Universal analyzer"
    echo
    echo "Uninstall:"
    echo "  $INSTALL_DIR/uninstall.sh"
    echo ========================================
}

uninstall() {
    log_info "Uninstalling app2nix..."
    
    systemctl stop app2nix || true
    systemctl disable app2nix || true
    rm -f /etc/systemd/system/app2nix.service
    rm -f /usr/share/applications/app2nix.desktop
    rm -f /etc/profile.d/app2nix.sh
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_DIR/app2nix"
    
    log_success "Uninstalled"
    exit 0
}

main() {
    echo "========================================"
    echo "  app2nix Installer v${VERSION}"
    echo "  For GLF-OS (NixOS)"
    echo "========================================"
    echo
    
    check_root
    check_dependencies
    download_app2nix
    create_system_service
    create_desktop_entry
    create_shell_aliases
    setup_firewall
    enable_autostart
    
    print_summary
}

# Handle arguments
case "${1:-install}" in
    uninstall)
        check_root
        uninstall
        ;;
    install|*)
        main
        ;;
esac