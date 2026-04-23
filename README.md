# app2nix

Convert .deb packages to NixOS expressions.

## Description

app2nix analyzes Debian .deb packages and generates NixOS expression files (default.nix) that can be used to install the package on NixOS.

## Features

- **Analyze .deb packages**: Extracts binary dependencies using dpkg and patchelf
- **Library translation**: Maps Debian library names to Nixpkgs package names
- **Auto-generates default.nix**: Creates ready-to-use Nix expressions

## Installation

```bash
pip install -e .
```

Requires: `dpkg-deb`, `patchelf`, `ldd`

## Usage

### Basic Usage

```bash
python main.py package.deb
```

### Download from URL

```bash
python main.py --url https://example.com/package.deb
```

### Output JSON descriptor

```bash
python main.py package.deb --json
```

### Print dependencies only

```bash
python main.py package.deb --print-deps
```

### Specify output directory

```bash
python main.py package.deb --output-dir ./mypackage
```

## Output Files

- `default.nix` - NixOS expression
- `descriptor.json` - JSON package descriptor (with `--json`)

## Project Structure

```
app2nix/
├── main.py              # CLI interface
├── analyze_deb.py     # Package analyzer
├── lib/
│   └── deb_to_nix.py   # Library translation dictionary
├── templates/
│   └── default.nix    # Nix template
├── utils/
│   └── __init__.py    # Utility functions
└── README.md
```

## Example

```bash
$ python main.py torguard-latest-amd64.deb
Generated: ./default.nix

$ cat default.nix
{ pkgs ? import <nixpkgs> {} }:
pkgs.stdenv.mkDerivation {
  pname = "torguard";
  version = "4.0";
  ...
  nativeBuildInputs = [
    pkgs.autoPatchelfHook
    pkgs.libdrm
    pkgs.mesa
    ...
  ];
}
```

## Usage on NixOS

```bash
nix-env -if default.nix
```

Or as a system package in configuration.nix.

## Limitations

- Hardcoded paths (e.g., `/sbin/ip`) won't work without modification
- Some proprietary packages may need manual adjustments
- Not a replacement for open-source alternatives

## License

MIT