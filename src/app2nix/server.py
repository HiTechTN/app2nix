#!/usr/bin/env python3
import ipaddress
import re
import shutil
import socket
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import httpx
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from app2nix.config import settings
from app2nix.core.analyzer import SUPPORTED_FORMATS as _FORMAT_MAP
from app2nix.core.analyzer import UniversalAnalyzer, detect_format
from app2nix.core.generator import NixGenerator
from app2nix.core.resolver import DependencyResolver
from app2nix.logging import logger

SUPPORTED_FORMATS = list(_FORMAT_MAP.keys())
_HOST_RE = re.compile(r"^\[?[A-Fa-f0-9:.]+\]?$")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https:; script-src 'self' https:; font-src 'self' https:; connect-src 'self' https:;",
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _looks_like_ip_address(host: str) -> bool:
    return bool(_HOST_RE.match(host.strip("[]")))


def _is_blocked_ip_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _is_blocked_hostname(hostname: str) -> bool:
    normalized = hostname.lower().rstrip(".")
    if normalized == "localhost" or normalized.endswith(".local"):
        return True
    if not _looks_like_ip_address(normalized):
        return False
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return _is_blocked_ip_address(ip)


def _validate_resolved_host(hostname: str) -> None:
    if _is_blocked_hostname(hostname):
        raise ValueError("URL host is not allowed")

    try:
        addr_infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Unable to resolve URL host") from exc

    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        if _is_blocked_ip_address(ip):
            raise ValueError("URL host resolves to a blocked address")


def _validate_download_url(raw_url: str) -> httpx.URL:
    url = httpx.URL(raw_url.strip())
    if url.scheme not in settings.allowed_url_schemes:
        raise ValueError(f"Unsupported URL scheme: {url.scheme}")
    if url.username or url.password:
        raise ValueError("URL credentials are not allowed")
    if not url.host:
        raise ValueError("URL host is required")
    _validate_resolved_host(url.host)
    return url


def _validate_redirect_url(raw_location: str, base_url: httpx.URL) -> httpx.URL:
    redirect_url = httpx.URL(urljoin(str(base_url), raw_location))
    if redirect_url.scheme not in settings.allowed_url_schemes:
        raise ValueError(f"Unsupported redirect URL scheme: {redirect_url.scheme}")
    if redirect_url.username or redirect_url.password:
        raise ValueError("Redirect URL credentials are not allowed")
    if not redirect_url.host:
        raise ValueError("Redirect URL host is required")
    _validate_resolved_host(redirect_url.host)
    return redirect_url


async def _download_url(url: str, temp_path: Path) -> None:
    current_url = _validate_download_url(url)
    timeout = httpx.Timeout(settings.download_timeout)
    limits = httpx.Limits(max_connections=1)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
    ) as client:
        redirects = 0
        with temp_path.open("wb") as fh:
            while True:
                async with client.stream("GET", current_url) as resp:
                    if resp.status_code in {301, 302, 303, 307, 308}:
                        location = resp.headers.get("location")
                        if not location:
                            raise ValueError("Redirect response missing Location header")
                        redirects += 1
                        if redirects > settings.max_url_redirects:
                            raise ValueError("Too many URL redirects")
                        current_url = _validate_redirect_url(location, current_url)
                        continue

                    resp.raise_for_status()
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > settings.max_download_size:
                            raise ValueError("Downloaded file exceeds maximum size")
                        fh.write(chunk)
                    break


def get_format(filename: str) -> str | None:
    return detect_format(filename)


async def _get_package_from_request(request) -> Path | JSONResponse:
    """Extract package file from request. Returns Path on success, JSONResponse on error."""
    form = await request.form()
    file = form.get("file")
    url = form.get("url")

    if url:
        temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_"))
        temp_path = temp_dir / "downloaded_package"
        try:
            await _download_url(str(url), temp_path)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return temp_path
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
            shutil.rmtree(temp_dir, ignore_errors=True)
            return JSONResponse(
                {"error": f"File too large. Max size: {max_size // 1024 // 1024}MB"},
                status_code=413,
            )
        temp_path.write_bytes(content)
        return temp_path
    else:
        return JSONResponse({"error": "No file or URL provided"}, status_code=400)


async def homepage(request):
    static_path = Path(__file__).parent.parent.parent / "static" / "index.html"
    if static_path.exists():
        return HTMLResponse(static_path.read_text())
    return HTMLResponse("<html><body><h1>app2nix</h1></body></html>")


async def api_root(request):
    return JSONResponse({
        "message": "app2nix API",
        "version": "3.1.0",
        "formats": SUPPORTED_FORMATS,
    })


async def analyze(request):
    temp_path = None
    try:
        result_or_error = await _get_package_from_request(request)
        if isinstance(result_or_error, JSONResponse):
            return result_or_error
        temp_path = result_or_error

        analyzer = UniversalAnalyzer()
        info = analyzer.analyze(str(temp_path))

        resolver = DependencyResolver()
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
            shutil.rmtree(temp_path.parent, ignore_errors=True)


async def generate(request):
    temp_path = None
    try:
        result_or_error = await _get_package_from_request(request)
        if isinstance(result_or_error, JSONResponse):
            return result_or_error
        temp_path = result_or_error

        analyzer = UniversalAnalyzer()
        info = analyzer.analyze(str(temp_path))

        resolver = DependencyResolver()
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
    middleware=[
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
        Middleware(SecurityHeadersMiddleware),
        Middleware(SessionMiddleware, secret_key=settings.secret_key),
    ],
)
