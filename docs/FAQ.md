# FAQ

Frequently Asked Questions about app2nix.

## General

### What is app2nix?

app2nix is a tool that converts Linux packages (.deb, .rpm, AppImage, etc.) into NixOS-native expressions that can run on NixOS/GLF-OS.

### Why use app2nix?

- Run ANY Linux application on NixOS
- No need to wait for upstream packaging
- Simple one-click conversion
- Free and open source

### What formats are supported?

- `.deb` - Debian/Ubuntu
- `.rpm` - Fedora/RHEL
- `.AppImage` - Portable
- `.flatpak` - Sandboxed
- `.snap` - Ubuntu
- `.tar.gz` - Source archives

## Installation

### How do I install on GLF-OS?

```bash
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/main/install.sh | bash
```

See [Installation Guide](INSTALL.md) for other methods.

### Do I need Nix installed?

Yes, to use the generated expressions:

```bash
# Install Nix
sh <(curl https://nixos.org/nix/install)
```

### What are the requirements?

- Python 3.10+
- `dpkg-deb` (for .deb)
- `patchelf` (for ELF fixing)
- `ldd` (library detection)

## Usage

### How do I convert a .deb file?

```bash
python main.py package.deb
```

This creates `default.nix` in the current directory.

### How do I use the generated Nix expression?

```bash
nix-env -if default.nix
```

Or add to NixOS configuration:

```nix
environment.systemPackages = with pkgs; [
  (import /path/to/default.nix)
];
```

### How do I convert from a URL?

```bash
python main.py --url https://example.com/package.deb
```

### Can I convert multiple files at once?

```bash
for f in *.deb; do
  python main.py "$f"
done
```

## Troubleshooting

### "command not found" errors

The generated expression may need dependencies that aren't in nixpkgs:

1. Check if package exists:
   ```bash
   nix-env -qaP | grep package-name
   ```

2. If not, you may need to add it to nixpkgs manually or use `fetchurl`.

### "library not found" errors

1. Check the library in nixpkgs:
   ```bash
   nix-env -qaP | grep library-name
   ```

2. Add missing package to `nativeBuildInputs` in generated Nix.

### PatchELF errors

1. Check binary format:
   ```bash
   file mybinary
   ```

2. Try manual fix:
   ```bash
   patchelf --set-rpath /run/current-system/sw/lib mybinary
   ```

### Application won't start

1. Check for hardcoded paths:
   ```bash
   strings mybinary | grep -E "^/(bin|sbin|usr)" | head -10
   ```

2. Fix paths using `substituteInPlace` in Nix expression.

### Desktop entry not found

Add to your Nix expression:

```nix
installPhase = ''
  mkdir -p $out/share/applications
  cp myapp.desktop $out/share/applications/
  update-desktop-database $out/share/applications
'';
```

### Icon not showing

```nix
installPhase = ''
  mkdir -p $out/share/icons/hicolor/48x48/apps
  cp myapp.png $out/share/icons/hicolor/48x48/apps/myapp.png
'';
```

## Limitations

### What doesn't work?

- Binaries with hardcoded absolute paths like `/sbin/ip`
- Proprietary codecs or libraries
- Packages requiring specific kernel versions
- Systemd services (need manual configuration)

### Can I convert Docker images?

Yes, export and analyze:

```bash
docker export mycontainer -o myapp.tar
python universal_analyze.py myapp.tar
```

### Can I convert Flatpak apps?

Yes, but Flatpak already is Nix-like. The converter extracts metadata:

```bash
python universal_analyze.py app.flatpak
```

## Contributing

### How do I contribute?

1. Fork the repo
2. Create a branch
3. Make changes
4. Submit PR

### How do I report bugs?

Open an issue at https://github.com/HiTechTN/app2nix/issues

### How do I request new features?

Open an issue with feature request label.

## License

MIT License - See [LICENSE](LICENSE)

## Support

### Where can I get help?

- GitHub Issues: https://github.com/HiTechTN/app2nix/issues
- Discord: https://discord.gg/app2nix

### Is there a commercial support?

Open an issue for enterprise support requests.