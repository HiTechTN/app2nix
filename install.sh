#!/usr/bin/env bash
#
# app2nix-installer.sh - Install app2nix on GLF-OS (NixOS)
# Usage: curl -sL "https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh" | sudo bash
#

VERSION="1.0.0"
REPO="HiTechTN/app2nix"
INSTALL_DIR="/opt/app2nix"
BIN_DIR="/usr/local/bin"
TARGET_USER="${SUDO_USER:-hitech}"

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
            # Install tools and also install fastapi via nix for web UI
            nix-env -iA nixpkgs.dpkg nixpkgs.patchelf nixpkgs.file nixpkgs.python3 nixpkgs.fastapi nixpkgs.uvicorn 2>/dev/null || true
            
            # Fix permissions for Nix tools
            log_info "Fixing Nix tools permissions..."
            for bin in dpkg-deb patchelf file; do
                for p in /run/current-system/sw/bin "$HOME/.nix-profile/bin"; do
                    if [ -f "$p/$bin" ]; then
                        chmod 755 "$p/$bin" 2>/dev/null || true
                    fi
                done
            done
            
            log_success "Done"
            ;;
        debian|ubuntu|linuxmint|pop|popos)
            log_info "Installing dependencies via apt..."
            apt-get update -qq
            apt-get install -y -qq dpkg patchelf file python3 python3-venv git curl >/dev/null 2>&1
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
    
    # Remove old venv if broken
    rm -rf .venv
    
    python3 -m venv .venv
    
    .venv/bin/pip install --upgrade pip
    
    # Install minimal packages (without pydantic which needs rust)
    .venv/bin/pip install starlette uvicorn python-multipart || {
        log_warn "pip install failed"
    }
    
    log_success "Python ready"
}

create_dirs() {
    log_info "Creating directories..."
    mkdir -p "$BIN_DIR"
    mkdir -p /usr/share/applications
    log_success "Directories created"
}

create_wrapper_scripts() {
    log_info "Creating commands..."
    
    NIX_PROF="/run/current-system/sw"
    USER_NIX="$HOME/.nix-profile"
    
    # Fix permissions for Nix tools - needs sudo
    log_info "Fixing Nix tools permissions..."
    chmod 755 "$NIX_PROF/bin/dpkg-deb" 2>/dev/null || true
    chmod 755 "$NIX_PROF/bin/patchelf" 2>/dev/null || true
    chmod 755 "$NIX_PROF/bin/file" 2>/dev/null || true
    chmod 755 "$USER_NIX/bin/dpkg-deb" 2>/dev/null || true
    chmod 755 "$USER_NIX/bin/patchelf" 2>/dev/null || true
    
    cat > "$BIN_DIR/app2nix" << ENDSCRIPT
#!/usr/bin/env bash
# app2nix CLI wrapper
export PATH="$NIX_PROF/bin:$USER_NIX/bin:/usr/local/bin:/usr/bin:/bin:\$PATH"
export LD_LIBRARY_PATH="$NIX_PROF/lib:$USER_NIX/lib:\$LD_LIBRARY_PATH"
chmod 755 "$NIX_PROF/bin/dpkg-deb" 2>/dev/null || true
chmod 755 "$NIX_PROF/bin/file" 2>/dev/null || true
exec /opt/app2nix/.venv/bin/python /opt/app2nix/main.py "\$@"
ENDSCRIPT
    chmod +x "$BIN_DIR/app2nix"

    cat > "$BIN_DIR/app2nix-server" << ENDSCRIPT
#!/usr/bin/env bash
# app2nix server wrapper  
export PATH="$NIX_PROF/bin:$USER_NIX/bin:/usr/local/bin:/usr/bin:/bin:\$PATH"
export LD_LIBRARY_PATH="$NIX_PROF/lib:$USER_NIX/lib:\$LD_LIBRARY_PATH"
exec /opt/app2nix/.venv/bin/python /opt/app2nix/server.py "\$@"
ENDSCRIPT
    chmod +x "$BIN_DIR/app2nix-server"
    
    log_success "Commands created"
}

configure_user_shell() {
    log_info "Configuring user shell for $TARGET_USER..."
    
    local user_home
    user_home=$(eval echo ~$TARGET_USER 2>/dev/null) || user_home="/home/$TARGET_USER"
    
    local shell_config="$user_home/.bashrc"
    [ -f "$user_home/.zshrc" ] && shell_config="$user_home/.zshrc"
    
    if [ -f "$shell_config" ]; then
        if ! grep -q "app2nix" "$shell_config" 2>/dev/null; then
            echo "" >> "$shell_config"
            echo "# app2nix - package to NixOS converter" >> "$shell_config"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$shell_config"
            echo "export PATH=\"\$HOME/.nix-profile/bin:\$PATH\"" >> "$shell_config"
            echo "alias app2nix='$BIN_DIR/app2nix'" >> "$shell_config"
            echo "alias app2nix-server='$BIN_DIR/app2nix-server'" >> "$shell_config"
        fi
    fi
    
    if [ -f "$user_home/.profile" ]; then
        if ! grep -q "app2nix" "$user_home/.profile" 2>/dev/null; then
            echo "" >> "$user_home/.profile"
            echo "# app2nix" >> "$user_home/.profile"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$user_home/.profile"
            echo "export PATH=\"\$HOME/.nix-profile/bin:\$PATH\"" >> "$user_home/.profile"
        fi
    fi
    
    log_success "Shell configured for $TARGET_USER"
}

create_desktop_entry() {
    log_info "Creating desktop entry..."
    
    cat > /usr/share/applications/app2nix.desktop << 'ENDDESKTOP'
[Desktop Entry]
Name=app2nix Web UI
Comment=Convert packages to NixOS
Exec=/usr/local/bin/app2nix-server
Icon=system-software-install
Type=Application
Categories=Development;System;
Terminal=false
StartupNotify=true
ENDDESKTOP
    
    update-desktop-database /usr/share/applications 2>/dev/null || true
    log_success "Desktop entry created"
}

print_summary() {
    echo
    echo "=========================================="
    echo "  app2nix v$VERSION installed!"
    echo "=========================================="
    echo
    echo "Web UI: http://localhost:8000"
    echo "CLI:  app2nix or /usr/local/bin/app2nix"
    echo
    echo "To use in current terminal:"
    echo "  source ~/.bashrc"
    echo "  app2nix --help"
    echo
    echo "To start web UI:"
    echo "  app2nix-server"
    echo "  # Then open http://localhost:8000"
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
    create_dirs
    create_python_venv
    create_wrapper_scripts
    configure_user_shell
    create_desktop_entry
    
    print_summary
}

main