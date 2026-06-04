# API Reference

REST API documentation for app2nix server.

## Base URL

```
http://localhost:8000
```

## Endpoints

### GET /

Returns the web UI.

**Response:** HTML page

### GET /api

API information endpoint.

**Response:**
```json
{
  "message": "app2nix API",
  "version": "3.0.1",
  "formats": [".deb", ".rpm", ".AppImage", ".appimage", ".tar.gz", ".tgz", ".tar", ".tar.xz", ".tar.bz2", ".flatpak", ".snap"]
}
```

### POST /analyze

Analyze a package file or URL.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` - Package file, OR `url` - URL to download

**Response:**
```json
{
  "name": "myapp",
  "version": "1.0.0",
  "format": "deb",
  "architecture": "amd64",
  "libraries": ["libgtk-3", "libdrm"],
  "nix_dependencies": ["gtk3", "libdrm"],
  "unresolved": []
}
```

**Examples:**
```bash
# From file
curl -X POST -F "file=@package.deb" http://localhost:8000/analyze

# From URL
curl -X POST -F "url=https://example.com/package.deb" http://localhost:8000/analyze
```

### POST /generate

Generate Nix expression from package.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` - Package file, OR `url` - URL to download

**Response:**
```json
{
  "name": "myapp",
  "version": "1.0.0",
  "architecture": "x86_64",
  "content": "{ pkgs ? import <nixpkgs> {} }: ...",
  "flake_content": "{ description = \"...\"; ... }",
  "install_guide": "# Installation Guide ...",
  "auto_install_script": "#!/bin/bash ...",
  "validation_passed": true,
  "unresolved_deps": []
}
```

**Examples:**
```bash
# From file
curl -X POST -F "file=@package.deb" http://localhost:8000/generate

# From URL
curl -X POST -F "url=https://example.com/package.deb" http://localhost:8000/generate
```

## Error Responses

| Status | Description |
|--------|-------------|
| 400 | Invalid file format or missing input |
| 413 | File too large |
| 500 | Internal server error |

**Error Example:**
```json
{
  "error": "Unsupported format. Supported: .deb, .rpm, ..."
}
```

## Supported Formats

| Format | Extension(s) | Description |
|--------|-------------|-------------|
| Debian | `.deb` | Debian/Ubuntu packages |
| RPM | `.rpm` | Red Hat/Fedora packages |
| AppImage | `.AppImage`, `.appimage` | Portable Linux apps |
| Flatpak | `.flatpak` | Flatpak bundles |
| Snap | `.snap` | Snap packages |
| Tarball | `.tar.gz`, `.tgz`, `.tar`, `.tar.xz`, `.tar.bz2` | Compressed archives |
