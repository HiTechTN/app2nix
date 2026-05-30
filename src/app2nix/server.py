#!/usr/bin/env python3
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from app2nix.config import settings
from app2nix.core.analyzer import UniversalAnalyzer
from app2nix.core.generator import NixGenerator
from app2nix.core.resolver import DependencyResolver
from app2nix.logging import logger

SUPPORTED_FORMATS = [".deb", ".rpm", ".AppImage", ".appimage", ".tar.gz", ".tgz", ".tar", ".flatpak", ".snap"]


def get_format(filename: str) -> str | None:
    name = filename.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        return ".tar.gz"
    ext = Path(name).suffix
    return ext if ext in SUPPORTED_FORMATS else None


async def homepage(request):
    static_path = Path(__file__).parent.parent.parent / "static" / "index.html"
    if static_path.exists():
        return HTMLResponse(static_path.read_text())
    return HTMLResponse("<html><body><h1>app2nix</h1></body></html>")


async def api_root(request):
    return JSONResponse({
        "message": "app2nix API",
        "version": "3.0.1",
        "formats": SUPPORTED_FORMATS,
    })


async def analyze(request):
    temp_path = None
    try:
        form = await request.form()
        file = form.get("file")
        url = form.get("url")

        if url:
            import urllib.request
            temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_"))
            temp_path = temp_dir / "downloaded_package"
            urllib.request.urlretrieve(url, str(temp_path))
        elif file:
            if not get_format(file.filename):
                return JSONResponse(
                    {"error": f"Unsupported format. Supported: {', '.join(SUPPORTED_FORMATS)}"},
                    status_code=400,
                )
            temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_"))
            temp_path = temp_dir / file.filename
            max_size = settings.max_upload_size
            content = await file.read(max_size + 1)
            if len(content) > max_size:
                return JSONResponse(
                    {"error": f"File too large. Max size: {max_size // 1024 // 1024}MB"},
                    status_code=413,
                )
            temp_path.write_bytes(content)
        else:
            return JSONResponse({"error": "No file or URL provided"}, status_code=400)

        analyzer = UniversalAnalyzer()
        info = analyzer.analyze(str(temp_path))

        resolver = DependencyResolver(settings.cache_db.expanduser())
        nix_deps, unresolved = resolver.resolve_all(info.dependencies)

        return JSONResponse({
            "name": info.name,
            "version": info.version,
            "format": info.format,
            "architecture": info.architecture,
            "libraries": info.dependencies,
            "nix_dependencies": nix_deps,
            "unresolved": unresolved,
        })
    except Exception as e:
        logger.exception("Error in analyze endpoint")
        return JSONResponse({"error": f"Analysis failed: {str(e)}"}, status_code=500)
    finally:
        if temp_path and temp_path.parent.exists():
            import shutil
            shutil.rmtree(temp_path.parent, ignore_errors=True)


async def generate(request):
    temp_path = None
    try:
        form = await request.form()
        file = form.get("file")
        url = form.get("url")

        if url:
            import urllib.request
            temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_"))
            temp_path = temp_dir / "downloaded_package"
            urllib.request.urlretrieve(url, str(temp_path))
        elif file:
            if not get_format(file.filename):
                return JSONResponse(
                    {"error": f"Unsupported format. Supported: {', '.join(SUPPORTED_FORMATS)}"},
                    status_code=400,
                )
            temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_"))
            temp_path = temp_dir / file.filename
            max_size = settings.max_upload_size
            content = await file.read(max_size + 1)
            if len(content) > max_size:
                return JSONResponse(
                    {"error": f"File too large. Max size: {max_size // 1024 // 1024}MB"},
                    status_code=413,
                )
            temp_path.write_bytes(content)
        else:
            return JSONResponse({"error": "No file or URL provided"}, status_code=400)

        analyzer = UniversalAnalyzer()
        info = analyzer.analyze(str(temp_path))

        resolver = DependencyResolver(settings.cache_db.expanduser())
        nix_deps, unresolved = resolver.resolve_all(info.dependencies)

        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=nix_deps, unresolved=unresolved)

        return JSONResponse({
            "name": info.name,
            "version": info.version,
            "architecture": info.architecture,
            "content": result.nix_content,
            "flake_content": result.flake_content,
            "install_guide": result.install_guide,
            "auto_install_script": result.install_script,
            "validation_passed": result.validation_passed,
            "unresolved_deps": unresolved,
        })
    except Exception as e:
        logger.exception("Error in generate endpoint")
        return JSONResponse({"error": f"Generation failed: {str(e)}"}, status_code=500)
    finally:
        if temp_path and temp_path.parent.exists():
            import shutil
            shutil.rmtree(temp_path.parent, ignore_errors=True)


routes = [
    Route("/", homepage),
    Route("/api", api_root),
    Route("/analyze", analyze, methods=["POST"]),
    Route("/generate", generate, methods=["POST"]),
]

app = Starlette(
    debug=settings.debug,
    routes=routes,
    middleware=[Middleware(SessionMiddleware, secret_key=settings.secret_key)],
)
