#!/usr/bin/env python3
"""
app2nix - Multi-format Package to NixOS Converter
"""

import os
import subprocess
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from analyze_deb import get_all_dependencies
from lib.deb_to_nix import translate_all

WORK_DIR = Path(tempfile.mkdtemp(prefix="app2nix_"))
SUPPORTED_FORMATS = [".deb", ".rpm", ".AppImage", ".appimage", ".tar.gz", ".tgz", ".tar", ".flatpak", ".snap"]
ARCH_MAP = {
    "amd64": "x86_64-linux",
    "i386": "i686-linux",
    "i686": "i686-linux",
    "arm64": "aarch64-linux",
    "armhf": "armv7l-linux",
    "arm": "armv7l-linux",
    "unknown": "x86_64-linux",
    "x86_64": "x86_64-linux",
}


def map_arch(arch: str) -> str:
    return ARCH_MAP.get(arch.lower(), arch)


def get_format(filename: str) -> str | None:
    name = filename.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        return ".tar.gz"
    ext = Path(name).suffix
    if ext in SUPPORTED_FORMATS:
        return ext
    return None


def analyze_any(package_path: str) -> dict:
    path = Path(package_path)
    fmt = get_format(path.name)
    if not fmt:
        return {"name": path.stem, "version": "1.0", "architecture": "x86_64", "format": "unknown", "dependencies": []}

    if fmt == ".deb":
        return get_all_dependencies(package_path)

    info = {"name": path.stem, "version": "1.0", "architecture": "x86_64", "format": fmt.lstrip("."), "dependencies": []}

    if fmt == ".AppImage" or fmt == ".appimage":
        try:
            os.chmod(package_path, 0o755)
            extract_dir = Path(tempfile.mkdtemp(prefix="appimage_"))
            subprocess.run([package_path, "--appimage-extract"], cwd=extract_dir,
                          capture_output=True, timeout=30)
            sf = extract_dir / "squashfs-root"
            if sf.exists():
                for root, _, files in os.walk(sf):
                    for f in files:
                        fp = Path(root) / f
                        if fp.is_file():
                            try:
                                r = subprocess.run(["file", "-b", str(fp)], capture_output=True, text=True, timeout=5)
                                if "ELF" in r.stdout and ("executable" in r.stdout or "shared object" in r.stdout):
                                    r2 = subprocess.run(["patchelf", "--print-needed", str(fp)],
                                                       capture_output=True, text=True, timeout=5)
                                    for lib in r2.stdout.splitlines():
                                        lib = lib.strip()
                                        if lib.startswith("lib") and ".so" in lib:
                                            name_only = lib[3:].split(".so")[0]
                                            if name_only:
                                                info["dependencies"].append(name_only)
                            except Exception:
                                pass
        except Exception:
            pass
        info["dependencies"] = sorted(set(info["dependencies"]))

    return info


async def homepage(request):
    static_path = Path(__file__).parent / "static" / "index.html"
    if static_path.exists():
        return HTMLResponse(static_path.read_text())
    return HTMLResponse("<html><body><h1>app2nix</h1></body></html>")


async def analyze(request):
    temp_path = None
    try:
        form = await request.form()
        file = form.get("file")
        url = form.get("url")

        if url:
            import urllib.request
            temp_path = WORK_DIR / "downloaded_package"
            urllib.request.urlretrieve(url, str(temp_path))
        elif file:
            if not get_format(file.filename):
                return JSONResponse({"error": f"Unsupported format. Supported: {', '.join(SUPPORTED_FORMATS)}"}, status_code=400)
            temp_path = WORK_DIR / file.filename
            content = await file.read()
            with open(temp_path, "wb") as f:
                f.write(content)
        else:
            return JSONResponse({"error": "No file or URL provided"}, status_code=400)

        info = analyze_any(str(temp_path))
        nix_deps = translate_all(info.get("dependencies", []))

        return JSONResponse({
            "name": info.get("name", "unknown"),
            "version": info.get("version", "1.0"),
            "format": info.get("format", "unknown"),
            "architecture": info.get("architecture", "amd64"),
            "libraries": info.get("dependencies", []),
            "nix_dependencies": nix_deps
        })
    except Exception as e:
        print(f"Error in analyze: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"Analysis failed: {str(e)}"}, status_code=500)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def build_nix_expression(pkg_name: str, pkg_version: str, pkg_arch: str, fmt: str, deps_lines: str) -> str:
    if fmt == "deb":
        extract = ('deb_file=$(find $src -name "*.deb" -o -name "*.ipk" 2>/dev/null | head -1); '
                   'if [ -n "$deb_file" ]; then '
                   '  dpkg-deb -x "$deb_file" $out; '
                   'else '
                   '  echo "ERROR: no .deb file found in $src"; exit 1; '
                   'fi')
        native = ["dpkg", "autoPatchelfHook"]
    elif fmt == "AppImage" or fmt == "appimage":
        extract = ('appimage=$(find $src -name "*.AppImage" -o -name "*.appimage" 2>/dev/null | head -1); '
                   'if [ -n "$appimage" ]; then '
                   '  chmod +x "$appimage"; '
                   '  "$appimage" --appimage-extract 2>/dev/null; '
                   '  if [ -d squashfs-root ]; then '
                   '    cp -r squashfs-root/* $out/; '
                   '    rm -rf squashfs-root; '
                   '  else '
                   '    echo "ERROR: appimage-extract failed"; exit 1; '
                   '  fi; '
                   'else '
                   '  echo "ERROR: no AppImage file found in $src"; exit 1; '
                   'fi')
        native = ["autoPatchelfHook"]
    else:
        extract = ('pkg_file=$(find $src -type f ! -name "*.nix" ! -name "*.sh" 2>/dev/null | head -1); '
                   'if [ -n "$pkg_file" ]; then '
                   '  mkdir -p $out/bin && cp "$pkg_file" $out/bin/; '
                   'else '
                   '  echo "ERROR: no package file found in $src"; exit 1; '
                   'fi')
        native = ["autoPatchelfHook"]

    native_inputs = "\n".join(f"    pkgs.{p}" for p in native)

    lines = [
        "{ pkgs ? import <nixpkgs> {} }:",
        "",
        "let",
        f'  pname = "{pkg_name}";',
        f'  version = "{pkg_version}";',
        "in pkgs.stdenv.mkDerivation {",
        "  inherit pname version;",
        "",
        "  src = ./.;",
        "",
        "  nativeBuildInputs = with pkgs; [",
        native_inputs,
        "  ];",
        "",
    ]
    if deps_lines:
        lines.append("  buildInputs = with pkgs; [")
        lines.append(deps_lines)
        lines.append("  ];")
        lines.append("")

    lines.extend([
        '  phases = [ "unpackPhase" "installPhase" "fixupPhase" ];',
        "",
        '  unpackPhase = "true";',
        "",
        "  installPhase = ''",
        "    mkdir -p $out",
        f"    {extract}",
        "",
        "    # Create bin directory and symlink all executables",
        "    mkdir -p $out/bin",
        '    for dir in $out/usr/bin $out/usr/local/bin $out/opt/*/bin; do',
        '      if [ -d "$dir" ]; then',
        '        for bin in "$dir"/*; do',
        '          if [ -f "$bin" ] && [ -x "$bin" ] && [ ! -d "$bin" ]; then',
        '            ln -sf "$bin" "$out/bin/$(basename "$bin")"',
        "          fi",
        "        done",
        "      fi",
        "    done",
        "",
        '    if [ -d "$out/usr/share" ]; then',
        "      mkdir -p $out/share",
        '      cp -r $out/usr/share/* $out/share/ 2>/dev/null || true',
        "    fi",
        "  '';",
        "",
        "  preFixup = ''",
        "    autoPatchelf $out",
        "  '';",
        "",
        '  meta = with pkgs.lib; {',
        '    description = "' + pkg_name + ' package converted for NixOS";',
        f'    platforms = [ "{pkg_arch}" ];',
        "    license = licenses.unfree;",
        "  };",
        "}",
    ])
    return "\n".join(lines)


async def generate(request):
    temp_path = None
    try:
        form = await request.form()
        file = form.get("file")
        url = form.get("url")

        if url:
            import urllib.request
            temp_path = WORK_DIR / "downloaded_package"
            urllib.request.urlretrieve(url, str(temp_path))
        elif file:
            if not get_format(file.filename):
                return JSONResponse({"error": f"Unsupported format. Supported: {', '.join(SUPPORTED_FORMATS)}"}, status_code=400)
            temp_path = WORK_DIR / file.filename
            content = await file.read()
            with open(temp_path, "wb") as f:
                f.write(content)
        else:
            return JSONResponse({"error": "No file or URL provided"}, status_code=400)

        info = analyze_any(str(temp_path))
        nix_deps = translate_all(info.get("dependencies", []))
        deps_lines = "\n".join(f"    pkgs.{dep}" for dep in nix_deps)

        pkg_name = info.get("name", "app")
        pkg_version = info.get("version", "1.0")
        pkg_arch = info.get("architecture", "x86_64-linux")
        fmt = info.get("format", "deb")

        pkg_arch = map_arch(pkg_arch)
        generated = build_nix_expression(pkg_name, pkg_version, pkg_arch, fmt, deps_lines)

        install_guide = f"""# Guide d'installation NixOS
# Package: {pkg_name} v{pkg_version}

## 1. Preparer
```bash
mkdir -p ~/nix-packages/{pkg_name}
cd ~/nix-packages/{pkg_name}
```

## 2. Placer le fichier
Copiez votre package dans ce dossier.

## 3. Creer default.nix
```bash
cat > default.nix << 'NIXEOF'
{generated}
NIXEOF
```

## 4. Installer

### Utilisateur
```bash
NIXPKGS_ALLOW_UNFREE=1 NIXPKGS_ALLOW_UNSUPPORTED_SYSTEM=1 nix-env -i -f default.nix
```

### Systeme (NixOS)
Ajoutez dans `/etc/nixos/configuration.nix`:
```nix
environment.systemPackages = with pkgs; [
  (callPackage ~/nix-packages/{pkg_name} {{}})
];
```
Puis:
```bash
sudo nixos-rebuild switch
```
"""

        auto_script = f"""#!/usr/bin/env bash
set -e
PACKAGE="{pkg_name}"
VERSION="{pkg_version}"
mkdir -p ~/nix-packages/$PACKAGE
cd ~/nix-packages/$PACKAGE
cat > default.nix << 'NIXEOF'
{generated}
NIXEOF
NIXPKGS_ALLOW_UNFREE=1 NIXPKGS_ALLOW_UNSUPPORTED_SYSTEM=1 nix-env -i -f default.nix
echo "Installed $PACKAGE v$VERSION"
"""

        return JSONResponse({
            "name": pkg_name,
            "version": pkg_version,
            "architecture": pkg_arch,
            "content": generated,
            "install_guide": install_guide,
            "auto_install_script": auto_script
        })
    except Exception as e:
        print(f"Error in generate: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"Generation failed: {str(e)}"}, status_code=500)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


async def api_root(request):
    return JSONResponse({"message": "app2nix API", "version": "1.0.0", "formats": SUPPORTED_FORMATS})


routes = [
    Route("/", homepage),
    Route("/api", api_root),
    Route("/analyze", analyze, methods=["POST"]),
    Route("/generate", generate, methods=["POST"]),
]

app = Starlette(
    debug=os.environ.get("DEBUG", "false").lower() == "true",
    routes=routes,
    middleware=[Middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "app2nix-secret"))]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
