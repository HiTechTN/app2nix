"""
Integration tests for the app2nix web server (app2nix/server.py).

Covers all endpoints: GET /, GET /api, POST /analyze, POST /generate,
plus the internal get_format() helper and error handling.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app2nix.models import PackageInfo
from app2nix.server import SUPPORTED_FORMATS, app, get_format


class AsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


class AsyncStreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


def mock_stream_response(mock_client, response):
    mock_client.stream = MagicMock(return_value=AsyncStreamContext(response))


async def iter_bytes(chunks):
    for chunk in chunks:
        yield chunk

# =============================================================================
# get_format  (pure-function helper)
# =============================================================================


class TestGetFormat:
    def test_deb(self):
        assert get_format("package.deb") == ".deb"

    def test_rpm(self):
        assert get_format("package.rpm") == ".rpm"

    def test_appimage(self):
        assert get_format("MyApp.appimage") == ".appimage"
        assert get_format("myapp.appimage") == ".appimage"

    def test_tar_gz(self):
        assert get_format("archive.tar.gz") == ".tar.gz"

    def test_tgz(self):
        assert get_format("archive.tgz") == ".tar.gz"

    def test_tar(self):
        assert get_format("archive.tar") == ".tar"

    def test_flatpak(self):
        assert get_format("app.flatpak") == ".flatpak"

    def test_snap(self):
        assert get_format("pkg.snap") == ".snap"

    def test_unsupported_returns_none(self):
        assert get_format("archive.xyz") is None
        assert get_format("image.png") is None

    def test_no_extension(self):
        assert get_format("Makefile") is None

    def test_supported_formats_list(self):
        """All entries in SUPPORTED_FORMATS should be recognised by get_format."""
        for ext in SUPPORTED_FORMATS:
            assert get_format(f"pkg{ext}") is not None, f"{ext} not recognised"


# =============================================================================
# GET /
# =============================================================================


class TestHomepage:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")

    @pytest.mark.asyncio
    async def test_contains_app2nix_in_body(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")
        assert "app2nix" in r.text
        assert "NixOS" in r.text

    @pytest.mark.asyncio
    async def test_serves_static_index_html(self):
        """The homepage should return the content of static/index.html."""
        static_path = (
            Path(__file__).resolve().parent.parent.parent / "static" / "index.html"
        )
        expected_content = static_path.read_text()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

        assert r.text == expected_content

    @pytest.mark.asyncio
    async def test_fallback_when_static_missing(self):
        """When static/index.html is missing, return a minimal fallback."""
        with (
            patch("app2nix.server.Path.exists", return_value=False),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get("/")
        assert r.status_code == 200
        assert "<h1>app2nix</h1>" in r.text


# =============================================================================
# GET /api
# =============================================================================


class TestApiRoot:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_json(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api")
        assert r.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_contains_expected_fields(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api")
        data = r.json()
        assert data["message"] == "app2nix API"
        assert data["version"] == "3.1.0"
        assert isinstance(data["formats"], list)
        assert ".deb" in data["formats"]
        assert ".appimage" in data["formats"]

    @pytest.mark.asyncio
    async def test_formats_match_supported(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api")
        data = r.json()
        assert set(data["formats"]) == set(SUPPORTED_FORMATS)


# =============================================================================
# POST /analyze  — error cases
# =============================================================================


class TestAnalyzeErrors:
    @pytest.mark.asyncio
    async def test_no_file_or_url_returns_400(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/analyze")
        assert r.status_code == 400
        assert "No file or URL provided" in r.json()["error"]

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_400(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/analyze",
                files={"file": ("archive.xyz", b"fake", "application/octet-stream")},
            )
        assert r.status_code == 400
        assert "Unsupported format" in r.json()["error"]

    @pytest.mark.asyncio
    async def test_file_too_large_returns_413(self):
        """File exceeding max_upload_size should return 413."""
        from app2nix.config import settings
        original = settings.max_upload_size
        settings.max_upload_size = 1024  # 1 KB max
        try:
            big_content = b"0" * 2048  # 2 KB — exceeds 1 KB limit
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("big.deb", big_content, "application/octet-stream")},
                )
            assert r.status_code == 413
            assert "too large" in r.json()["error"]
        finally:
            settings.max_upload_size = original


# =============================================================================
# POST /analyze  — successful analysis (mocked)
# =============================================================================


class TestAnalyzeSuccess:
    FAKE_INFO = PackageInfo(
        name="test-pkg",
        version="2.0.1",
        architecture="amd64",
        format="deb",
        dependencies=["ssl", "z"],
    )
    FAKE_RESOLVED = ["openssl", "zlib"]
    FAKE_UNRESOLVED = []

    @pytest.mark.asyncio
    async def test_analyze_with_file_upload(self):
        """Upload a valid .deb file and get analysis results."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = self.FAKE_INFO
            mock_analyzer_cls.return_value = mock_analyzer

            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = (
                self.FAKE_RESOLVED,
                self.FAKE_UNRESOLVED,
            )
            mock_resolver_cls.return_value = mock_resolver

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={
                        "file": ("test.deb", b"fake deb content", "application/octet-stream")
                    },
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "test-pkg"
        assert data["version"] == "2.0.1"
        assert data["format"] == "deb"
        assert data["architecture"] == "amd64"
        assert data["libraries"] == ["ssl", "z"]
        assert data["nix_dependencies"] == ["openssl", "zlib"]
        assert data["unresolved"] == []

    @pytest.mark.asyncio
    async def test_analyze_with_url(self):
        """Pass a URL and verify the endpoint tries to download it."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
            patch("app2nix.server.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="url-pkg",
                version="1.0",
                architecture="x86_64",
                format="deb",
                dependencies=[],
            )
            mock_analyzer_cls.return_value = mock_analyzer
            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = ([], [])
            mock_resolver_cls.return_value = mock_resolver

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {}
            mock_resp.aiter_bytes = lambda: iter_bytes([b"fake-deb-content"])
            mock_client = MagicMock()
            mock_stream_response(mock_client, mock_resp)
            mock_httpx_cls.return_value = AsyncClientContext(mock_client)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    data={"url": "https://example.com/package.deb"},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "url-pkg"

    @pytest.mark.asyncio
    async def test_analyze_internal_error_returns_500(self):
        """Internal exceptions should be caught and return 500."""
        with patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.side_effect = RuntimeError("internal failure")
            mock_analyzer_cls.return_value = mock_analyzer

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={
                        "file": ("test.deb", b"fake", "application/octet-stream")
                    },
                )

        assert r.status_code == 500
        assert "internal failure" in r.json()["error"]


# =============================================================================
# POST /generate  — error cases
# =============================================================================


class TestGenerateErrors:
    @pytest.mark.asyncio
    async def test_no_file_or_url_returns_400(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/generate")
        assert r.status_code == 400
        assert "No file or URL provided" in r.json()["error"]

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_400(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/generate",
                files={"file": ("file.xyz", b"data", "application/octet-stream")},
            )
        assert r.status_code == 400
        assert "Unsupported format" in r.json()["error"]

    @pytest.mark.asyncio
    async def test_file_too_large_returns_413(self):
        from app2nix.config import settings
        original = settings.max_upload_size
        settings.max_upload_size = 1024  # 1 KB max
        try:
            big_content = b"0" * 2048  # 2 KB — exceeds 1 KB limit
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={"file": ("big.deb", big_content, "application/octet-stream")},
                )
            assert r.status_code == 413
        finally:
            settings.max_upload_size = original


# =============================================================================
# POST /generate  — successful generation (mocked)
# =============================================================================


class TestGenerateSuccess:
    FAKE_INFO = PackageInfo(
        name="my-app",
        version="3.0.1",
        architecture="arm64",
        format="rpm",
        dependencies=["ssl"],
    )
    FAKE_RESOLVED = ["openssl"]
    FAKE_UNRESOLVED = []

    @pytest.mark.asyncio
    async def test_generate_with_file_upload(self):
        """Upload a file and verify the Nix expression is generated."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
            patch("app2nix.server.NixGenerator") as mock_generator_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = self.FAKE_INFO
            mock_analyzer_cls.return_value = mock_analyzer

            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = (
                self.FAKE_RESOLVED,
                self.FAKE_UNRESOLVED,
            )
            mock_resolver_cls.return_value = mock_resolver

            mock_generator = MagicMock()
            mock_result = MagicMock()
            mock_result.nix_content = "{ pkgs }: pkgs.stdenv.mkDerivation { ... }"
            mock_result.flake_content = None
            mock_result.install_guide = "Install guide text"
            mock_result.install_script = "#!/bin/bash\\necho install"
            mock_result.validation_passed = True
            mock_generator.generate_default_nix.return_value = mock_result
            mock_generator_cls.return_value = mock_generator

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={
                        "file": ("myapp.rpm", b"fake rpm", "application/octet-stream")
                    },
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "my-app"
        assert data["version"] == "3.0.1"
        assert data["architecture"] == "arm64"
        assert "mkDerivation" in data["content"]
        assert data["install_guide"] == "Install guide text"
        assert data["auto_install_script"] is not None
        assert data["validation_passed"] is True
        assert data["unresolved_deps"] == []

    @pytest.mark.asyncio
    async def test_generate_internal_error_returns_500(self):
        with patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.side_effect = ValueError("parse error")
            mock_analyzer_cls.return_value = mock_analyzer

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={
                        "file": ("test.deb", b"x", "application/octet-stream")
                    },
                )

        assert r.status_code == 500
        assert "parse error" in r.json()["error"]

    @pytest.mark.asyncio
    async def test_generate_with_url(self):
        """Generate endpoint should also support URL downloads."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
            patch("app2nix.server.NixGenerator") as mock_generator_cls,
            patch("app2nix.server.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="url-pkg", version="1.0", format="deb", dependencies=[]
            )
            mock_analyzer_cls.return_value = mock_analyzer
            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = ([], [])
            mock_resolver_cls.return_value = mock_resolver
            mock_generator = MagicMock()
            mock_result = MagicMock()
            mock_result.nix_content = "nix expression"
            mock_result.flake_content = None
            mock_result.install_guide = ""
            mock_result.install_script = ""
            mock_result.validation_passed = True
            mock_generator.generate_default_nix.return_value = mock_result
            mock_generator_cls.return_value = mock_generator

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {}
            mock_resp.aiter_bytes = lambda: iter_bytes([b"fake-rpm-content"])
            mock_client = MagicMock()
            mock_stream_response(mock_client, mock_resp)
            mock_httpx_cls.return_value = AsyncClientContext(mock_client)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    data={"url": "https://example.com/package.rpm"},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "url-pkg"


# =============================================================================
# POST /analyze  — edge cases
# =============================================================================


class TestAnalyzeEdgeCases:
    @pytest.mark.asyncio
    async def test_analyze_url_download_failure_returns_500(self):
        """URL download that raises an HTTP error should return 500."""
        import httpx

        with (
            patch("app2nix.server.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_client = MagicMock()
            mock_client.stream = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    message="Not Found",
                    request=MagicMock(),
                    response=MagicMock(status_code=404),
                )
            )
            mock_httpx_cls.return_value = AsyncClientContext(mock_client)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    data={"url": "https://example.com/missing.deb"},
                )

        assert r.status_code == 500
        assert "Analysis failed" in r.json()["error"]

    @pytest.mark.asyncio
    async def test_analyze_with_unresolved_deps(self):
        """Analyze should surface unresolved dependencies in the response."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="dep-pkg",
                version="1.0",
                architecture="amd64",
                format="deb",
                dependencies=["ssl", "unknown-lib", "z"],
            )
            mock_analyzer_cls.return_value = mock_analyzer

            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = (
                ["openssl"],
                ["unknown-lib"],
            )
            mock_resolver_cls.return_value = mock_resolver

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={
                        "file": ("dep.deb", b"fake", "application/octet-stream")
                    },
                )

        assert r.status_code == 200
        data = r.json()
        assert data["nix_dependencies"] == ["openssl"]
        assert "unknown-lib" in data["unresolved"]


# =============================================================================
# POST /generate  — edge cases
# =============================================================================


class TestGenerateEdgeCases:
    @pytest.mark.asyncio
    async def test_generate_url_download_failure_returns_500(self):
        """URL download failure in generate should return 500."""
        import httpx

        with (
            patch("app2nix.server.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_client = MagicMock()
            mock_client.stream = MagicMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_httpx_cls.return_value = AsyncClientContext(mock_client)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    data={"url": "https://example.com/pkg.deb"},
                )

        assert r.status_code == 500
        assert "Generation failed" in r.json()["error"]

    @pytest.mark.asyncio
    async def test_generate_with_unresolved_deps(self):
        """Generate should include unresolved deps in the response."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
            patch("app2nix.server.NixGenerator") as mock_generator_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="dep-app",
                version="2.0",
                architecture="amd64",
                format="deb",
                dependencies=["ssl", "mystery"],
            )
            mock_analyzer_cls.return_value = mock_analyzer

            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = (
                ["openssl"],
                ["mystery"],
            )
            mock_resolver_cls.return_value = mock_resolver

            mock_generator = MagicMock()
            mock_result = MagicMock()
            mock_result.nix_content = "{ pkgs }: pkgs.stdenv.mkDerivation {}"
            mock_result.flake_content = "nix = { }"
            mock_result.install_guide = "guide"
            mock_result.install_script = "script"
            mock_result.validation_passed = False
            mock_generator.generate_default_nix.return_value = mock_result
            mock_generator_cls.return_value = mock_generator

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={
                        "file": ("dep.deb", b"fake", "application/octet-stream")
                    },
                )

        assert r.status_code == 200
        data = r.json()
        assert "mystery" in data["unresolved_deps"]
        assert data["validation_passed"] is False

    @pytest.mark.asyncio
    async def test_generate_internal_error_from_resolver(self):
        """Resolver failure should be caught and return 500."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="err-pkg", version="1.0", format="deb", dependencies=[]
            )
            mock_analyzer_cls.return_value = mock_analyzer
            mock_resolver = MagicMock()
            mock_resolver.resolve_all.side_effect = OSError("disk full")
            mock_resolver_cls.return_value = mock_resolver

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={
                        "file": ("err.deb", b"x", "application/octet-stream")
                    },
                )

        assert r.status_code == 500
        assert "disk full" in r.json()["error"]



# =============================================================================
# GET /nonexistent  (404)
# =============================================================================


class TestNotFound:
    @pytest.mark.asyncio
    async def test_unknown_route_returns_404(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/nonexistent")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_api_route_returns_405(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/api")
        assert r.status_code == 405
