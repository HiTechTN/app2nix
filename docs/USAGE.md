# Usage Guide

Complete usage guide for app2nix.

## Command Line Interface

### Basic Usage

```bash
# Analyze a .deb file
python main.py package.deb

# Specify output directory
python main.py package.deb --output-dir ./myapp

# Download from URL
python main.py --url https://example.com/package.deb

# Print dependencies only
python main.py package.deb --print-deps
```

### Options

| Option | Description |
|--------|-------------|
| `file` | Package file to analyze |
| `--output, -o` | Output nix file |
| `--output-dir, -d` | Output directory (default: .) |
| `--json` | Output JSON descriptor |
| `--print-deps` | Print dependencies only |
| `--url` | URL to download package from |
| `--verbose, -v` | Verbose output |

## Universal Analyzer

```bash
# Analyze any supported format
python universal_analyze.py package.deb
python universal_analyze.py package.rpm
python universal_analyze.py package.AppImage
python universal_analyze.py package.tar.gz
```

## Web Interface

Start the web server:

```bash
python server.py
```

Open http://localhost:8000 in your browser.

Features:
- Drag & drop package upload
- URL import
- One-click conversion
- Nix expression download

## API Usage

### Analyze Package

```bash
curl -X POST -F "file=@package.deb" http://localhost:8000/analyze
```

Response:
```json
{
  "name": "myapp",
  "version": "1.0.0",
  "architecture": "amd64",
  "libraries": ["libdrm", "libgtk-3"],
  "nix_dependencies": ["libdrm", "gtk3"]
}
```

### Generate Nix Expression

```bash
curl -X POST -F "file=@package.deb" http://localhost:8000/generate
```

Response:
```json
{
  "name": "myapp",
  "version": "1.0.0",
  "content": "{ pkgs ? import <nixpkgs> {} }:\n\npkgs.stdenv.mkDerivation {...}"
}
```

### Download from URL

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/package.deb"}' \
  http://localhost:8000/download
```

## Examples

### Convert Firefox

```bash
python main.py firefox.deb
```

Generated `default.nix`:
```nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.stdenv.mkDerivation {
  pname = "firefox";
  version = "120.0";
  src = ./.;

  nativeBuildInputs = [
    pkgs.autoPatchelfHook
    pkgs.libdrm
    pkgs.nss
    pkgs.cdp
  ];
  
  installPhase = ''
    ...
  '';
}
```

### Convert from AppImage

```bash
python universal_analyze.py myapp.AppImage
```

The analyzer will:
1. Extract AppImage contents
2. Find ELF binaries
3. Detect shared libraries
4. Generate Nix expression

### Batch Conversion

```bash
# Process multiple files
for deb in *.deb; do
  python main.py "$deb" --output-dir "${deb%.deb}"
done
```

## Using Generated Nix

### Test Locally

```bash
cd myapp
nix-env -if default.nix
```

### Install System-Wide

Add to NixOS configuration:

```nix
# configuration.nix
{ config, pkgs, ... }:

{
  environment.systemPackages = with pkgs; [
    (import ./myapp/default.nix)
  ];
}
```

### Build Package

```bash
nix-build default.nix
```

## Troubleshooting

### Missing Dependencies

If you get " library not found" errors:

1. Check the library exists in nixpkgs:
   ```bash
   nix-env -qaP | grep library-name
   ```

2. Add missing packages to `nativeBuildInputs`

### PatchELF Errors

If patchelf fails:

1. Check binary format:
   ```bash
   file mybinary
   ```

2. Try manual fix:
   ```bash
   patchelf --set-rpath /run/current-system/sw/lib mybinary
   ```

### Path Issues

If application can't find files:

1. Check for hardcoded paths:
   ```bash
   strings mybinary | grep -E "^/" | head -20
   ```

2. Use `substituteInPlace` to fix paths in wrapper

## Next Steps

- See [API Reference](API.md) for programmatic usage
- See [Examples](EXAMPLES.md) for real-world conversion examples
- See [FAQ](FAQ.md) for common questions