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

        content = f'''{{ pkgs ? import <nixpkgs> {{}} }}:

pkgs.stdenv.mkDerivation {{
  pname = "{info.get("name", "app")}";
  version = "{info.get("version", "1.0")}";
  src = ./.;

  nativeBuildInputs = [
    pkgs.autoPatchelfHook
{deps_lines}  ];

  installPhase = '';
}}
'''

        return JSONResponse({
            "name": info.get("name", "app"),
            "version": info.get("version", "1.0"),
            "content": content
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
