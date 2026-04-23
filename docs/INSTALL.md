# Installation Guide

This guide covers all installation methods for app2nix.

## Requirements

- Python 3.10+
- Linux with glibc (Debian/Ubuntu/Fedora/NixOS)
- Required tools: `dpkg-deb`, `patchelf`, `ldd`

## Install via Script (GLF-OS)

```bash
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash
```

This will:
- Download app2nix to `/opt/app2nix`
- Create systemd service
- Create desktop entry
- Enable autostart
- Configure firewall

## Install via pip

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install app2nix
pip install -e .

# Or install from PyPI (when available)
pip install app2nix
```

## Install from Source

```bash
# Clone repository
git clone https://github.com/HiTechTN/app2nix.git
cd app2nix

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

## Docker Installation

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    dpkg-dev patchelf file \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app2nix
COPY . /app2nix

RUN pip install -r requirements.txt

EXPOSE 8000
CMD ["python", "server.py"]
```

Build and run:

```bash
docker build -t app2nix .
docker run -p 8000:8000 app2nix
```

## NixOS Installation

Add to your `configuration.nix`:

```nix
{ pkgs, ... }:

let
  app2nix = pkgs.fetchFromGitHub {
    owner = "HiTechTN";
    repo = "app2nix";
    rev = "main";
    sha256 = "...";
  };
in

environment.systemPackages = with pkgs; [
  app2nix
];
```

Or use `nix-env`:

```bash
nix-env -i -f https://github.com/HiTechTN/app2nix/archive/main.tar.gz
```

## Verify Installation

```bash
# Check CLI
python main.py --version

# Check server
python server.py &
# Open http://localhost:8000

# Check systemd service (GLF-OS)
systemctl status app2nix
```

## Uninstall

```bash
# Via script (GLF-OS)
/opt/app2nix/uninstall.sh

# Or manually
systemctl stop app2nix
systemctl disable app2nix
rm -rf /opt/app2nix
```