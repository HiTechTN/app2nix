# Changelog

All notable changes to **app2nix** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.1] — Unreleased

### Added
- **CI: MSRV 1.80.0 matrix** — `rust-check` job now tests against both `stable` and `1.80.0`
- **Rustdoc workflow** (`.github/workflows/rustdoc.yml`) — independent GitHub Pages deployment for rustdoc, triggered on Rust file changes
- **AUTHORS.md** — maintainer, contributors, and special thanks
- **CHANGELOG.md** — this file
- **Badges**:
  - Rust API docs (rustdoc) badge in README
  - MSRV badge (`rustc 1.80+`)
  - PyPI downloads badge
  - Python versions supported badge
  - PyPI License badge

### Changed
- **Version bump** `3.0.0` → `3.0.1` across `pyproject.toml`, `Cargo.toml`, CLI `--version`, server `/api`
- **CI: toolchain simplification** — Removed `toolchain: stable` from 4 workflows (`tests.yml`, `release.yml`, `docker.yml`, `rustdoc.yml`); `rust-toolchain.toml` (`channel = "1.80.0"`) is now the single source of truth
- **Pages workflow** — rustdoc build steps removed from `pages.yml` (now handled by `rustdoc.yml`)
- **`docs/_site/index.html`** — rustdoc links changed to absolute URLs (`https://app2nix.dev/rustdoc/...`)
- **README** — Acknowledgments section now links to `AUTHORS.md`

### Fixed
- Server `/api` endpoint returns `"version": "3.0.1"` (was hardcoded to `"3.0.0"`)

---

## [3.0.0] — 2026-05-29

### Added
- **Rust Cargo workspace** with 13 crates (`cli`, `core`, `detector`, `extractor`, `analyzer`, `resolver`, `nixgen`, `patcher`, `desktop`, `installer`, `sandbox`, `fhs`, `plugins`)
- **245+ Rust tests** — unit, integration, and doctests across all crates
- **Rust-based pipeline** — `Detector` → `Extractor` → `Analyzer` → `Patcher` → `NixGen` → `Installer` → `DesktopIntegrator`
- **Dependency resolver** — maps 150+ libraries to Nixpkgs attributes
- **CLI binary** (`app2nix`) — clap-based with `install`, `uninstall`, `list`, `inspect`, `build`, `doctor`, `cache`, `clean` commands
- **CI/CD workflows**:
  - `ci.yml` — `cargo check`, `cargo test`, `cargo fmt`, `cargo clippy`
  - `tests.yml` — Python + Rust tests with coverage
  - `docker.yml` — Docker image build and push to `ghcr.io/hitechtn/app2nix`
  - `release.yml` — GitHub Release with binary artifact + Docker image
  - `ruff.yml` — Python linting with Ruff
  - `mypy.yml` — Python type checking with mypy
  - `pages.yml` — GitHub Pages deployment for `app2nix.dev`
- **Docker support** — multi-stage Dockerfile, `docker-compose.yml`
- **Flake templates** — updated `flake.nix.j2` and `derivation.nix.j2`
- **FHS compatibility** — `fhs-env.nix.j2` template for `buildFHSUserEnv`
- **Badges** — CI, Tests, Rust, Ruff, Mypy, Clippy, Coverage, Docker, Release, PyPI, Docs

### Changed
- **Project restructured** to `src/` layout with clear module separation
- **Flake template** — uses `pkgs.callPackage ./derivation.nix` instead of inline derivation
- **`nixpkgs` channel** — updated from `nixos-24.05` to `nixos-unstable`

### Fixed
- AppImage extraction error handling and `unsquashfs` availability check
- Multi-format support and architecture mapping
- Existing installation detection and conflict resolution
- Docker-free start/stop on NixOS
- NixOS detection for derivatives (GLF-OS)
- Various ruff, clippy, and mypy lint errors

---

## [2.0.1] — 2026-05-20

### Added
- `app2nix gui` command entry point
- Auto-generated `secret_key` for web server

### Changed
- Install script improvements for NixOS

### Fixed
- Handle existing installations and package conflicts
- Docker-free start/stop on NixOS
- Broadened NixOS detection for derivatives (GLF-OS)

---

## [2.0.0] — 2026-05-18

### Added
- **Project restructured** to `src/app2nix/` layout
- **Format-specific analyzers** — `.deb`, `.rpm`, `.AppImage`, `.tar.gz`, Flatpak, Snap
- **Nix template system** — Jinja2 templates for `default.nix` and `flake.nix`
- **Comprehensive test suite** — unit tests for resolver, generator, and analyzers
- **CI workflows** — initial GitHub Actions configuration

### Changed
- Core refactored into modular `core/` package (analyzer, resolver, generator, validator)
- Moved from flat structure to organized `src/app2nix/` namespace

---

## [1.2.0] — 2026-05-15

### Added
- **PyQt6 native GUI** (`app2nix_gui.py`)
- **Internationalization (i18n)** — English, French, Arabic translations
- **Dark/light theme support**
- AppImage offset fix for proper extraction
- HTML documentation site with multiple pages

### Fixed
- Lint errors (ruff I001, F841)
- CI workflows updated for Node.js 24

---

## [1.1.0] — 2026-05-10

### Added
- Multi-format support (`.deb`, `.rpm`, `.AppImage`, `.tar.gz`, Flatpak, Snap)
- Architecture mapping (amd64, i386, arm64, armhf)
- Install pipeline with auto-install script
- French documentation and support assistant
- Interactive conversion process animation
- Video creation scripts

### Fixed
- Server async file read and frontend error handling
- FormData handling in converter UI
- Various lint and syntax errors

---

## [1.0.0] — 2026-04-24

### Added
- Initial release of **app2nix**
- Web UI for package upload and conversion
- Starlette web server with REST API (`/analyze`, `/generate`)
- Dependency resolver for Nixpkgs library mapping
- Nix expression generator (`default.nix`, `flake.nix`)
- Desktop entry integration
- GitHub Pages demo site
- Docker support
- Installer script for NixOS/GLF-OS

---

[3.0.1]: https://github.com/HiTechTN/app2nix/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/HiTechTN/app2nix/compare/v2.0.1...v3.0.0
[2.0.1]: https://github.com/HiTechTN/app2nix/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/HiTechTN/app2nix/compare/v1.2.0...v2.0.0
[1.2.0]: https://github.com/HiTechTN/app2nix/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/HiTechTN/app2nix/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/HiTechTN/app2nix/releases/tag/v1.0.0
