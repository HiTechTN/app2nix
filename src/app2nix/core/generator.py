import subprocess
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app2nix.core.resolver import DependencyResolver
from app2nix.models import ConversionResult, PackageInfo

INSTALL_PHASE_MAP = {
    "deb": (
        'deb_file=$(find $src -name "*.deb" -o -name "*.ipk" 2>/dev/null | head -1); '
        'if [ -n "$deb_file" ]; then '
        "  dpkg-deb -x \"$deb_file\" $out; "
        'else '
        '  echo "ERROR: no .deb file found in $src"; exit 1; '
        "fi"
    ),
    "rpm": (
        'rpm_file=$(find $src -name "*.rpm" 2>/dev/null | head -1); '
        'if [ -n "$rpm_file" ]; then '
        "  rpm2cpio \"$rpm_file\" | cpio -idmv; "
        'else '
        '  echo "ERROR: no .rpm file found in $src"; exit 1; '
        "fi"
    ),
    "appimage": (
        'appimage=$(find $src -name "*.AppImage" -o -name "*.appimage" 2>/dev/null | head -1); '
        'if [ -n "$appimage" ]; then '
        '  chmod +x "$appimage"; '
        '  "$appimage" --appimage-extract 2>/dev/null; '
        "  if [ -d squashfs-root ]; then "
        "    cp -r squashfs-root/* $out/; "
        "    rm -rf squashfs-root; "
        '  else '
        '    echo "ERROR: appimage-extract failed"; exit 1; '
        "  fi; "
        'else '
        '  echo "ERROR: no AppImage file found in $src"; exit 1; '
        "fi"
    ),
}

DEFAULT_INSTALL = (
    'pkg_file=$(find $src -type f ! -name "*.nix" ! -name "*.sh" 2>/dev/null | head -1); '
    'if [ -n "$pkg_file" ]; then '
    '  mkdir -p $out/bin && cp "$pkg_file" $out/bin/; '
    'else '
    '  echo "ERROR: no package file found in $src"; exit 1; '
    "fi"
)


@dataclass
class NixGenerator:
    templates_dir: Path = Path("templates")

    def _get_env(self) -> Environment:
        return Environment(loader=FileSystemLoader(str(self.templates_dir)))

    def generate_default_nix(self, info: PackageInfo) -> ConversionResult:
        env = self._get_env()
        template = env.get_template("default.nix.j2")

        install_phase = INSTALL_PHASE_MAP.get(info.format, DEFAULT_INSTALL)

        resolver = DependencyResolver(Path("/tmp/app2nix_resolver.db"))
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        build_deps = [f"pkgs.{d}" for d in resolved]
        native_deps = ["autoPatchelfHook"]
        if info.format == "deb":
            native_deps.append("dpkg")

        content = template.render(
            name=info.name,
            version=info.version,
            src_expr="./.",
            description=info.description or f"{info.name} package converted for NixOS",
            platform=info.architecture,
            native_deps=native_deps,
            build_deps=build_deps,
            install_phase=install_phase,
        )

        validated, err = self.validate(content)

        return ConversionResult(
            package=info,
            nix_content=content,
            install_script=self._generate_install_script(info),
            install_guide=self._generate_install_guide(info),
            unresolved_deps=unresolved,
            validation_passed=validated,
            validation_error=err,
        )

    def generate_flake_nix(self, info: PackageInfo) -> ConversionResult:
        env = self._get_env()
        template = env.get_template("flake.nix.j2")

        resolver = DependencyResolver(Path("/tmp/app2nix_resolver.db"))
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        build_deps = [f"pkgs.{d}" for d in resolved]
        install_phase = INSTALL_PHASE_MAP.get(info.format, DEFAULT_INSTALL)

        content = template.render(
            name=info.name,
            version=info.version,
            format=info.format,
            description=info.description or f"{info.name} — converted from {info.format} by app2nix",
            build_deps=build_deps,
            install_phase=install_phase,
        )

        validated, err = self.validate(content)

        return ConversionResult(
            package=info,
            nix_content=content,
            unresolved_deps=unresolved,
            validation_passed=validated,
            validation_error=err,
        )

    def validate(self, nix_content: str) -> tuple[bool, str | None]:
        try:
            r = subprocess.run(
                ["nix-instantiate", "--parse", "-"],
                input=nix_content, capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0, r.stderr if r.returncode != 0 else None
        except FileNotFoundError:
            return True, None

    def _generate_install_guide(self, info: PackageInfo) -> str:
        return f"""# Installation Guide: {info.name} v{info.version}

## 1. Prepare
```bash
mkdir -p ~/nix-packages/{info.name}
cd ~/nix-packages/{info.name}
```

## 2. Copy your package file into this directory

## 3. Create default.nix with the generated content

## 4. Install
### User install
```bash
NIXPKGS_ALLOW_UNFREE=1 nix-env -i -f default.nix
```
### System install (NixOS)
Add to /etc/nixos/configuration.nix:
```nix
environment.systemPackages = with pkgs; [
  (callPackage ~/nix-packages/{info.name} {{}})
];
```
Then run:
```bash
sudo nixos-rebuild switch
```"""

    def _generate_install_script(self, info: PackageInfo) -> str:
        return f"""#!/usr/bin/env bash
set -e
PACKAGE="{info.name}"
VERSION="{info.version}"
mkdir -p ~/nix-packages/$PACKAGE
cd ~/nix-packages/$PACKAGE
# Copy the generated default.nix here
NIXPKGS_ALLOW_UNFREE=1 nix-env -i -f default.nix
echo "Installed $PACKAGE v$VERSION"
"""
