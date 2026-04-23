# Examples

Real-world conversion examples for common applications.

## Firefox

### 1. Download Firefox .deb

```bash
wget https://download.mozilla.org/?product=firefox-latest&os=linux64
```

### 2. Analyze

```bash
python main.py firefox*.deb --print-deps
```

### 3. Generate Nix

```bash
python main.py firefox*.deb --output-dir ./firefox
```

### 4. Install

```bash
cd firefox
nix-env -if default.nix
```

### Generated default.nix

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
    pkgs.cairo
    pkgs.pango
    pkgs.freetype
  ];

  installPhase = ''
    runHook preInstall
    mkdir -p $out/lib/firefox
    cp -r firefox/* $out/lib/firefox/
    mkdir -p $out/bin
    ln -s $out/lib/firefox/firefox $out/bin/firefox
    runHook postInstall
  '';
}
```

## Tor Browser

### 1. Download

```bash
wget https://www.torproject.org/dist/torbrowser/13.0/tor-browser-linux-x86_64-13.0.tar.xz
```

### 2. Analyze

```bash
python universal_analyze.py tor-browser-linux-x86_64-13.0.tar.xz
```

### 3. Generate

The analyzer will detect:
- Browser binaries
- Shared libraries
- Hardcoded paths

### 4. Manual Fixes

Some applications need manual fixes:

```nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.stdenv.mkDerivation {
  pname = "tor-browser";
  version = "13.0";
  src = ./tor-browser;

  nativeBuildInputs = [
    pkgs.autoPatchelfHook
    pkgs.stdenv.cc
  ];

  postFixup = ''
    # Fix hardcoded paths
    substituteInPlace $out/Browser/TorBrowser/Data/Tor/torrc \
      --replace /opt/tor-browser $out
  '';
}
```

## VS Code

### 1. Download .deb

```bash
wget https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64
```

### 2. Analyze

```bash
python main.py vscode*.deb
```

### 3. Generated

```nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.stdenv.mkDerivation {
  pname = "vscode";
  version = "1.85";
  src = ./.;

  nativeBuildInputs = [
    pkgs.autoPatchelfHook
    pkgs.electron
    pkgs.nodejs_20
    pkgs.python3
  ];

  installPhase = ''
    mkdir -p $out/lib/vscode
    cp -r usr/share/code $out/lib/vscode/
    cp -r opt $out/
    
    # Fix desktop entry
    substituteInPlace $out/lib/vscode/share/applications/code.desktop \
      --replace /opt/ $out/
    
    mkdir -p $out/bin
    ln -s $out/lib/vscode/bin/code $out/bin/code
  '';
}
```

## Discord

### 1. Download

```bash
wget https://discord.com/api/download?platform=linux
```

### 2. Analyze

```bash
python universal_analyze.py Discord*.deb
```

### 3. Issues

Discord may need:

```nix
# Add to nativeBuildInputs
pkgs.libappindicator
pkgs.libdbusmenu
pkgs.libsecret
```

## Docker to NixOS

### Convert docker-compose to Nix

If you have a Docker application:

1. Export container:

```bash
docker export myapp -o myapp.tar
```

2. Analyze:

```bash
python universal_analyze.py myapp.tar
```

3. Generate Nix expression:

The analyzer will find all binaries and libraries, then generate appropriate Nix derivation.

## AppImage to NixOS

### 1. Extract AppImage

```bash
./myapp.AppImage --appimage-extract
```

### 2. Analyze extracted squashfs:

```bash
python universal_analyze.py myapp.AppImage
```

### 3. Generate

```nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.stdenv.mkDerivation {
  pname = "myapp";
  version = "1.0";
  src = ./squashfs-root;

  nativeBuildInputs = [ pkgs.autoPatchelfHook ];

  installPhase = ''
    cp -r $src/* $out/
    # Fix desktop files
    substituteInPlace $out/*.desktop \
      --replace @APPDIR@ $out
  '';
}
```

## Multi-Platform Build

For packages that support multiple architectures:

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  version = "1.0.0";
in

pkgs.stdenv.mkDerivation {
  pname = "myapp";
  inherit version;
  src = ./myapp;

  nativeBuildInputs = [ pkgs.autoPatchelfHook ];

  unpackPhase = ''
    mkdir -p $out
    tar -xf $src
  '';

  installPhase = ''
    cp -r myapp-*/* $out/
  '';

  meta = with pkgs; {
    description = "My Application";
    platforms = pkgs.platforms.linux;
  };
}
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Convert to NixOS

on:
  release:
    types: [published]

jobs:
  convert:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Download artifact
        run: |
          wget -O app.deb ${{ github.event.release.asset_url }}
      
      - name: Convert
        run: |
          python main.py app.deb --output-dir nix/
      
      - name: Create PR
        run: |
          gh pr create -B nixpkgs -T nix \
            -body "Auto-generated Nix expression"
```

### GitLab CI

```yaml
convert:
  image: python:3.11
  script:
    - pip install app2nix
    - app2nix app.deb --output-dir nix/
  artifacts:
    paths:
      - nix/
```