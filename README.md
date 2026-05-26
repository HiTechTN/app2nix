# app2nix - Universal Package to NixOS Converter

<p align="center">

[![Stars](https://img.shields.io/github/stars/HiTechTN/app2nix)](https://github.com/HiTechTN/app2nix/stargazers)
[![Forks](https://img.shields.io/github/forks/HiTechTN/app2nix)](https://github.com/HiTechTN/app2nix/network/members)
[![License](https://img.shields.io/github/license/HiTechTN/app2nix)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/HiTechTN/app2nix/total)](https://github.com/HiTechTN/app2nix/releases)

</p>

<div align="center">

### Transform any Linux package into a NixOS native application with one click

[![CI](https://github.com/HiTechTN/app2nix/actions/workflows/ci.yml/badge.svg)](https://github.com/HiTechTN/app2nix/actions)
[![Tests](https://github.com/HiTechTN/app2nix/workflows/Tests/badge.svg)](https://github.com/HiTechTN/app2nix/actions)
[![Docker Build](https://github.com/HiTechTN/app2nix/workflows/Docker%20Build%20and%20Push/badge.svg)](https://github.com/HiTechTN/app2nix/actions)
[![Release](https://img.shields.io/github/v/release/HiTechTN/app2nix?include_prereleases&sort=semver)](https://github.com/HiTechTN/app2nix/releases/latest)

[Documentation](docs/) · [Report Bug](https://github.com/HiTechTN/app2nix/issues) · [Request Feature](https://github.com/HiTechTN/app2nix/issues)

</div>

---

## ✨ What is app2nix?

**app2nix** converts Linux packages from any format (`.deb`, `.rpm`, `.AppImage`, Flatpak, Snap, tarball) into ready-to-use NixOS expressions. No more manual dependency hunting - let app2nix handle the complexity.

### 🎯 Why NixOS?

- **Reproducible builds** - Same result every time
- **Declarative config** - Your entire system in code
- **Rollback support** - Never break your system
- **Atomic updates** - All or nothing
- **Multi-version** - Run different versions side by side

---

## 🚀 Features

| Feature | Description |
|---------|-------------|
| 🌐 **Web UI** | Beautiful drag-and-drop interface for instant conversion |
| ⚡ **Auto-Dependencies** | Automatically detects and maps 150+ libraries to Nixpkgs |
| 📦 **Universal Formats** | Supports .deb, .rpm, .AppImage, Flatpak, Snap, tar.gz |
| 🖥️ **CLI Tool** | Scriptable conversion for CI/CD pipelines |
| 🔌 **REST API** | Integrate into your own applications |
| 🔧 **Auto-PatchELF** | Automatic rpath fixing and binary patching |
| 🎨 **Nix Expression Generator** | Outputs production-ready `default.nix` files |

---

## 📸 Screenshots

### Web Interface
![Homepage](docs/screenshots/screenshots/01-homepage.png)

### Features Section
![Features](docs/screenshots/screenshots/02-features.png)

### Package Converter
![Converter](docs/screenshots/screenshots/04-converter.png)

### API Documentation
![API Docs](docs/screenshots/screenshots/05-api-docs.png)

---

## 📦 Supported Formats

| Format | Extension | Distros | Status |
|--------|----------|---------|--------|
| 🟠 Debian | `.deb` | Ubuntu, Debian, Mint | ✅ Stable |
| 🔴 RPM | `.rpm` | Fedora, RHEL, CentOS | ✅ Stable |
| 🟡 AppImage | `.AppImage` | Universal | ✅ Stable |
| 🔵 Flatpak | `.flatpak` | Universal | 🟡 Beta |
| 🟢 Snap | `.snap` | Ubuntu | 🟡 Beta |
| ⚪ Tarball | `.tar.gz` | Universal | ✅ Stable |

---

## 🛠️ Quick Start

### Installation

```bash
# From PyPI (recommended)
pip install app2nix

# With GUI
pip install "app2nix[gui]"

# From source
git clone https://github.com/HiTechTN/app2nix.git
cd app2nix && pip install -e .
```

### CLI

```bash
# Convert a .deb
app2nix convert package.deb

# Convert a .rpm
app2nix convert package.rpm --output-dir ./myapp

# Also generate flake.nix (default in v3.0)
app2nix convert package.deb

# Print dependencies
app2nix convert package.deb --print-deps

# Start the web server
app2nix serve

# Graphical interface (requires pip install "app2nix[gui]")
app2nix gui
```

### Web UI

```bash
app2nix serve
# Open http://localhost:8000
```

### Docker

```bash
docker run -p 8000:8000 -e APP2NIX_SECRET_KEY=mysecret ghcr.io/hitechtn/app2nix:latest
```

---

## 🌐 Interactive Demo

Try app2nix without installing:

```bash
# Using Docker
docker run -p 8000:8000 ghcr.io/hitechtn/app2nix:latest

# Open http://localhost:8000
```

Or test online at **[app2nix.dev](https://hitechtn.github.io/app2nix)**

---

## 📚 Documentation

| Resource | Description |
|----------|-------------|
| [📖 Full Documentation](docs/index.html) | Complete HTML guide — install, CLI, API, examples, architecture, FAQ |
| [Installation Guide](docs/INSTALL.md) | How to install app2nix |
| [Usage Guide](docs/USAGE.md) | Detailed usage instructions |
| [API Reference](docs/API.md) | REST API documentation |
| [Examples](docs/EXAMPLES.md) | Real-world examples |
| [FAQ](docs/FAQ.md) | Frequently asked questions |

---

## 🏗️ Architecture

```
app2nix/
├── src/app2nix/
│   ├── __init__.py       # Package init, version
│   ├── cli.py            # Typer CLI (app2nix convert/serve/gui)
│   ├── config.py         # Settings via pydantic-settings
│   ├── models.py         # PackageInfo, ConversionResult (pydantic)
│   ├── logging.py        # Structured logging
│   ├── exceptions.py     # Custom exceptions
│   ├── core/
│   │   ├── analyzer.py       # UniversalAnalyzer
│   │   ├── analyzers/        # Format-specific analyzers
│   │   ├── generator.py      # NixGenerator (default.nix, flake.nix)
│   │   ├── resolver.py       # DependencyResolver (150+ libs)
│   │   └── validator.py      # Nix expression validator
│   ├── gui/
│   │   ├── __init__.py       # run_gui() entry point
│   │   ├── main_window.py    # PyQt6 GUI with QThread workers
│   │   ├── i18n.py           # Internationalization
│   │   ├── theme.py          # Light/dark theme
│   │   └── templates/        # Jinja2 install guide
│   └── server.py         # Starlette web server
├── static/
│   └── index.html        # Web UI
├── templates/
│   ├── default.nix.j2    # Nix expression template
│   └── flake.nix.j2      # Flake expression template
├── tests/                # Unit & GUI tests
├── docs/                 # Documentation
├── main.py               # Deprecated → use app2nix CLI
├── server.py             # Deprecated → use app2nix serve
└── app2nix_gui.py        # Deprecated → use app2nix gui
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## 📊 Project Stats

| Metric | Badge |
|--------|-------|
| ⭐ Stars | [![Stars](https://img.shields.io/github/stars/HiTechTN/app2nix)](https://github.com/HiTechTN/app2nix/stargazers) |
| 🍴 Forks | [![Forks](https://img.shields.io/github/forks/HiTechTN/app2nix)](https://github.com/HiTechTN/app2nix/network/members) |
| 🐛 Issues | [![Issues](https://img.shields.io/github/issues/HiTechTN/app2nix)](https://github.com/HiTechTN/app2nix/issues) |
| ⬇️ Downloads | [![Downloads](https://img.shields.io/github/downloads/HiTechTN/app2nix/total)](https://github.com/HiTechTN/app2nix/releases) |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [NixOS](https://nixos.org/) - For the amazing package manager
- [Nixpkgs](https://github.com/NixOS/nixpkgs) - For the extensive package collection
- [dpkg](https://wiki.debian.org/dpkg) - For .deb package handling
- Contributors and users of app2nix

---

<div align="center">

Made with ❤️ by [HiTechTN](https://github.com/HiTechTN)

⭐ Star this repo if app2nix helps you!

</div>