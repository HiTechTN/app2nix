# app2nix - Universal Package to NixOS Converter

<p align="center">
  <img src="https://img.shields.io/pypi/v/app2nix" alt="PyPI">
  <img src="https://img.shields.io/github/license/HiTechTN/app2nix" alt="License">
  <img src="https://img.shields.io/github/actions/workflow/status/HiTechTN/app2nix/tests" alt="Tests">
  <a href="https://discord.gg/app2nix"><img src="https://img.shields.io/discord/123456789" alt="Discord"></a>
</p>

> Transform .deb, .rpm, AppImage, Flatpak and more into NixOS native applications with a single click.

## Features

- **Universal Support** - Convert from any Linux package format
- **Auto-Dependencies** - Automatic library detection and Nixpkgs mapping
- **One-Click** - Web UI for easy conversion
- **CLI + API** - Command-line and REST API
- **Auto-PatchELF** - Automatic rpath fixing

## Supported Formats

| Format | Extension | Description |
|--------|------------|-------------|
| Debian | `.deb` | Debian/Ubuntu packages |
| RPM | `.rpm` | Fedora/RHEL packages |
| AppImage | `.AppImage` | Portable applications |
| Flatpak | `.flatpak` | Sandboxed applications |
| Snap | `.snap` | Ubuntu Snap packages |
| Tarball | `.tar.gz` | Source archives |

## Quick Start

### Web UI

```bash
cd ~/projects/app2nix
source .venv/bin/activate
python server.py
# Open http://localhost:8000
```

### CLI

```bash
# Analyze a .deb file
python main.py package.deb

# Generate default.nix
python main.py package.deb --output-dir ./mypackage

# Universal analyzer
python universal_analyze.py package.AppImage
```

### Install on GLF-OS

```bash
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash
```

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Usage Guide](docs/USAGE.md)
- [API Reference](docs/API.md)
- [Examples](docs/EXAMPLES.md)
- [FAQ](docs/FAQ.md)

## Architecture

```
app2nix/
├── main.py                 # CLI interface
├── server.py              # FastAPI web server
├── universal_analyze.py  # Universal package analyzer
├── lib/
│   └── deb_to_nix.py     # Debian → Nixpkgs mapping
├── static/
│   └── index.html       # Web UI
├── templates/
│   └── default.nix      # Nix expression template
├── install.sh           # GLF-OS installer
└── docs/                # Documentation
```

## License

MIT License - See [LICENSE](LICENSE)