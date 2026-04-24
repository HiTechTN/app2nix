#!/usr/bin/env bash
#
# app2nix-installer.sh - Install app2nix on GLF-OS (NixOS)
# Usage: curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | sudo bash
#

set -e

VERSION="1.0.0"
REPO="HiTechTN/app2nix"
INSTALL_DIR="/opt/app2nix"
BIN_DIR="/usr/local/bin"
DATA_DIR="/var/lib/app2nix"

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

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif [ -f /run/current-system/sw/etc/os-release ]; then
        . /run/current-system/sw/etc/os-release
        echo "$ID"
    else
        echo "nixos"
    fi
}

install_dependencies_nix() {
    log_info "Installing dependencies via Nix..."
    
    if command -v nix-env &> /dev/null; then
        nix-env -iA nixpkgs.dpkg nixpkgs.patchelf nixpkgs.file
        log_success "Dependencies installed via Nix"
    else
        log_error "Nix not found. Please install Nix first:"
        echo "  sh <(curl https://nixos.org/nix/install)"
        exit 1
    fi
}

install_dependencies_apt() {
    log_info "Installing dependencies via apt..."
    apt-get update
    apt-get install -y dpkg patchelf file python3 git curl
}

install_dependencies() {
    local os=$(detect_os)
    log_info "Detected OS: $os"
    
    case "$os" in
        nixos|glfos)
            install_dependencies_nix
            ;;
        debian|ubuntu|linuxmint|pop)
            install_dependencies_apt
            ;;
        *)
            log_warn "Unknown OS: $os, trying apt..."
            install_dependencies_apt || log_warn "Could not install dependencies automatically"
            ;;
    esac
}

download_app2nix() {
    log_info "Downloading app2nix v${VERSION}..."
    
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    if command -v git &> /dev/null; then
        rm -rf .git
        git init
        git remote add origin "https://github.com/${REPO}.git"
        git fetch origin
        git checkout -b master origin/master
    else
        curl -sL "https://github.com/${REPO}/archive/refs/heads/master.tar.gz" | tar xz
        mv app2nix-master/* .
        mv app2nix-master/.* . 2>/dev/null || true
        rm -rf app2nix-master
    fi
    
    log_success "Downloaded to $INSTALL_DIR"
}

create_python_venv() {
    log_info "Setting up Python virtual environment..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not found"
        return 1
    fi
    
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install fastapi uvicorn pydantic python-multipart
    
    log_success "Python environment ready"
}

create_system_service() {
    log_info "Creating systemd service..."
    
    cat > /etc/systemd/system/app2nix.service << EOF
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
Environment="PATH=$INSTALL_DIR/.venv/bin:/run/wrappers/bin:/run/current-system/sw/bin:\$PATH"

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
Exec=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/server.py
Icon=system-software-install
Type=Application
Categories=Development;System;
Keywords=nixos;package;converter;deb;rpm;appimage;
Terminal=false
StartupNotify=true
EOF
    
    update-desktop-database /usr/share/applications 2>/dev/null || true
    
    log_success "Desktop entry created"
}

create_shell_aliases() {
    log_info "Creating shell aliases..."
    
    cat > /etc/profile.d/app2nix.sh << EOF
# app2nix shell aliases
export APP2NIX_DIR=$INSTALL_DIR
alias app2nix='$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py'
alias app2nix-server='$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/server.py'
alias app2nix-analyze='$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/universal_analyze.py'
EOF
    
    chmod +x /etc/profile.d/app2nix.sh
    
    log_success "Aliases created"
}

create_wrapper_script() {
    log_info "Creating wrapper scripts..."
    
    cat > "$BIN_DIR/app2nix" << EOF
#!/usr/bin/env bash
# Wrapper for app2nix CLI
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/main.py" "\$@"
EOF
    chmod +x "$BIN_DIR/app2nix"

    cat > "$BIN_DIR/app2nix-server" << EOF
#!/usr/bin/env bash  
# Wrapper for app2nix server
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/server.py" "\$@"
EOF
    chmod +x "$BIN_DIR/app2nix-server
    
    log_success "Wrapper scripts created"
}

setup_nix_channel() {
    log_info "Setting up Nix channels..."
    
    if command -v nix-channel &> /dev/null; then
        nix-channel --add https://nixos.org/channels/nixpkgs-unstable nixpkgs 2>/dev/null || true
        nix-channel --update 2>/dev/null || true
        log_success "Nix channels configured"
    else
        log_warn "Nix not installed, skipping channel setup"
    fi
}

enable_autostart() {
    log_info "Enabling autostart..."
    
    systemctl enable app2nix.service 2>/dev/null || true
    systemctl start app2nix.service 2>/dev/null || true
    
    log_success "Autostart enabled"
}

create_uninstall_script() {
    log_info "Creating uninstall script..."
    
    cat > "$INSTALL_DIR/uninstall.sh" << EOF
#!/usr/bin/env bash
set -e

echo "Uninstalling app2nix..."

systemctl stop app2nix 2>/dev/null || true
systemctl disable app2nix 2>/dev/null || true
rm -f /etc/systemd/system/app2nix.service
rm -f /usr/share/applications/app2nix.desktop
rm -f /etc/profile.d/app2nix.sh
rm -f $BIN_DIR/app2nix
rm -f $BIN_DIR/app2nix-server
rm -rf $INSTALL_DIR

echo "app2nix uninstalled!"
EOF
    chmod +x "$INSTALL_DIR/uninstall.sh"
    
    log_success "Uninstall script created"
}

print_summary() {
    echo
    echo "========================================"
    echo "  app2nix v${VERSION} installed successfully!"
    echo "========================================"
    echo
    echo "Web UI:    http://localhost:8000"
    echo "Install:  $INSTALL_DIR"
    echo "CLI:      app2nix"
    echo
    echo "Commands:"
    echo "  app2nix <package.deb>     # CLI"
    echo "  app2nix-server            # Web UI"
    echo "  app2nix-analyze         # Universal analyzer"
    echo
    echo "Uninstall:"
    echo "  $INSTALL_DIR/uninstall.sh"
    echo "========================================"
}

main() {
    echo "========================================"
    echo "  app2nix Installer v${VERSION}"
    echo "  For GLF-OS (NixOS)"
    echo "========================================"
    echo
    
    check_root
    install_dependencies
    download_app2nix
    create_python_venv
    create_system_service
    create_desktop_entry
    create_shell_aliases
    create_wrapper_script
    setup_nix_channel
    create_uninstall_script
    enable_autostart
    
    print_summary
}

case "${1:-install}" in
    uninstall)
        check_root
        if [ -f "$INSTALL_DIR/uninstall.sh" ]; then
            "$INSTALL_DIR/uninstall.sh"
        else
            log_error "Uninstall script not found"
            exit 1
        fi
        ;;
    install|*)
        main
        ;;
esac