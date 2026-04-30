#!/usr/bin/env python3
"""
app2nix - Minimal Web Server using starlette
"""

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


async def homepage(request):
    """Serve the landing page."""
    static_path = Path(__file__).parent / "static" / "index.html"
    if static_path.exists():
        return HTMLResponse(static_path.read_text())
    return HTMLResponse("""<html><body><h1>app2nix</h1><p>Upload a .deb file</p></body></html""")


async def analyze(request):
    """Analyze a .deb file or URL."""
    form = await request.form()
    file = form.get("file")
    url = form.get("url")

    temp_path = None
    try:
        if url:
            import urllib.request
            print(f"Downloading {url}...")
            temp_path = WORK_DIR / "downloaded_package"
            urllib.request.urlretrieve(url, str(temp_path))
        elif file:
            if not file.filename.endswith(".deb"):
                return JSONResponse({"error": "File must be .deb"}, status_code=400)
            temp_path = WORK_DIR / file.filename
            with open(temp_path, "wb") as f:
                f.write(file.read())
        else:
            return JSONResponse({"error": "No file or URL provided"}, status_code=400)

        info = get_all_dependencies(str(temp_path))
        nix_deps = translate_all(info.get("dependencies", []))

        return JSONResponse({
            "name": info.get("name", "unknown"),
            "version": info.get("version", "1.0"),
            "architecture": info.get("architecture", "amd64"),
            "libraries": info.get("dependencies", []),
            "nix_dependencies": nix_deps
        })
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


async def generate(request):
    """Generate Nix expression."""
    form = await request.form()
    file = form.get("file")
    url = form.get("url")

    temp_path = None
    try:
        if url:
            import urllib.request
            print(f"Downloading {url}...")
            temp_path = WORK_DIR / "downloaded_package"
            urllib.request.urlretrieve(url, str(temp_path))
        elif file:
            if not file.filename.endswith(".deb"):
                return JSONResponse({"error": "File must be .deb"}, status_code=400)
            temp_path = WORK_DIR / file.filename
            with open(temp_path, "wb") as f:
                f.write(file.read())
        else:
            return JSONResponse({"error": "No file or URL provided"}, status_code=400)

        info = get_all_dependencies(str(temp_path))
        nix_deps = translate_all(info.get("dependencies", []))

        deps_lines = ""
        for dep in nix_deps:
            deps_lines += f"    pkgs.{dep}\n"

        pkg_name = info.get("name", "app")
        pkg_version = info.get("version", "1.0")
        pkg_arch = info.get("architecture", "x86_64-linux")

        content = """{{ pkgs ? import <nixpkgs> {{}} }}:

pkgs.stdenv.mkDerivation {{
  pname = "{pkg_name}";
  version = "{pkg_version}";
  src = ./.;

  nativeBuildInputs = [
    pkgs.autoPatchelfHook
{deps_lines}  ];

  installPhase = '';
}}
""".format(pkg_name=pkg_name, pkg_version=pkg_version, deps_lines=deps_lines)

        install_guide = """# Guide d'installation complet pour NixOS
# Package: {pkg_name} v{pkg_version}

## Etape 1: Preparer le fichier .deb
mkdir -p ~/nix-packages/{pkg_name}
cd ~/nix-packages/{pkg_name}
# Telechargez votre fichier .deb ici ou copiez-le
# wget URL_VERS_VOTRE_DEB

## Etape 2: Creer le fichier default.nix
cat > default.nix << 'EOF'
{content}
EOF

## Etape 3: Methode A - Installation systeme (recommande pour NixOS)
# 1. Copier le fichier .deb dans le dossier actuel
# 2. Ajouter au fichier de configuration NixOS:

# Editer /etc/nixos/configuration.nix
sudo nano /etc/nixos/configuration.nix

# Ajouter dans la section environment.systemPackages:
environment.systemPackages = with pkgs; [
  (callPackage ~/nix-packages/{pkg_name} {{}})
  # ... autres packages ...
];

# Puis rebuild:
sudo nixos-rebuild switch

## Etape 3: Methode B - Installation utilisateur (plus simple)
nix-env -i -f default.nix

## Installation automatique (une seule commande)
# Pour installation systeme (necessite sudo):
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install-package.sh | bash -s -- {pkg_name} {pkg_version}

## Commande d'installation complete automatique
# Cette commande fait tout automatiquement:
cat > install-automatic.sh << 'AUTO'
#!/usr/bin/env bash
set -e
PACKAGE="{pkg_name}"
VERSION="{pkg_version}"
DEB_URL="VOTRE_URL_DEB_ICI"  # CHANGEZ CETTE URL

echo "[1/5] Creation du dossier..."
mkdir -p ~/nix-packages/$PACKAGE
cd ~/nix-packages/$PACKAGE

echo "[2/5] Telechargement du package..."
if [ -n "$DEB_URL" ] && [ "$DEB_URL" != "VOTRE_URL_DEB_ICI" ]; then
    wget -O $PACKAGE.deb "$DEB_URL"
else
    echo "Erreur: Veuillez modifier DEB_URL dans le script"
    exit 1
fi

echo "[3/5] Creation du fichier Nix..."
cat > default.nix << 'EOF'
{content}
EOF

echo "[4/5] Installation..."
nix-env -i -f default.nix

echo "[5/5] Verification..."
which $PACKAGE || echo "Installation terminee: $PACKAGE"
echo "OK $PACKAGE v$VERSION installe avec succes!"
AUTO

chmod +x install-automatic.sh
echo "Executez: ./install-automatic.sh"

## Ressources pour debutants
# Documentation NixOS: https://nixos.org/manual/nixos/stable/
# Recherche de packages: https://search.nixos.org/packages
# Forum NixOS: https://discourse.nixos.org/

## Verifier l'installation
which {pkg_name} 2>/dev/null && echo "OK {pkg_name} est installe" || echo "ERREUR {pkg_name} n'est pas installe"
nix-env --query | grep {pkg_name} 2>/dev/null && echo "OK Present dans nix-env" || echo "Package dans systeme NixOS"
""".format(pkg_name=pkg_name, pkg_version=pkg_version, content=content)

        auto_script = """#!/usr/bin/env bash
set -e
PACKAGE="{pkg_name}"
VERSION="{pkg_version}"

echo "Installation automatique de $PACKAGE v$VERSION"
echo "Ce script va installer le package avec toutes ses dependances Nix."

mkdir -p ~/nix-packages/$PACKAGE
cd ~/nix-packages/$PACKAGE

cat > default.nix << 'EOF'
{content}
EOF

echo "Installation en cours..."
nix-env -i -f default.nix

echo "Installation terminee!"
which $PACKAGE 2>/dev/null && $PACKAGE --version 2>/dev/null || echo "Package installe: $PACKAGE"
""".format(pkg_name=pkg_name, pkg_version=pkg_version, content=content)

        return JSONResponse({
            "name": pkg_name,
            "version": pkg_version,
            "architecture": pkg_arch,
            "content": content,
            "install_guide": install_guide,
            "auto_install_script": auto_script
        })
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


async def api_root(request):
    """API info."""
    return JSONResponse({"message": "app2nix API", "version": "1.0.0"})


routes = [
    Route("/", homepage),
    Route("/api", api_root),
    Route("/analyze", analyze, methods=["POST"]),
    Route("/generate", generate, methods=["POST"]),
]

app = Starlette(
    debug=True,
    routes=routes,
    middleware=[Middleware(SessionMiddleware, secret_key="app2nix-secret")]
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
