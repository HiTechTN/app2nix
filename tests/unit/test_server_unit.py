"""
Unit tests for app2nix/server.py — edge cases, error handling, and boundary conditions.

Complements the integration tests in tests/integration/test_server.py by covering:
  1. _get_package_from_request edge cases (URL failures, boundary sizes)
  2. Temp file cleanup verification
  3. get_format with new formats (tar.bz2, tar.xz)
  4. Upload size boundary tests (exactly at limit, just under)
  5. Both file and URL in request (URL takes precedence)
  6. Generate with unresolved dependencies
  7. Homepage fallback edge cases
"""

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app2nix.models import PackageInfo
from app2nix.server import SUPPORTED_FORMATS, app, get_format


# =============================================================================
# get_format — additional edge cases for new formats
# =============================================================================


class TestGetFormatExtended:
    def test_tar_bz2(self):
        assert get_format("archive.tar.bz2") == ".tar.bz2"

    def test_tar_xz(self):
        assert get_format("archive.tar.xz") == ".tar.xz"

    def test_txz_alias(self):
        assert get_format("archive.txz") == ".tar.xz"

    def test_tbz2_alias(self):
        assert get_format("archive.tbz2") == ".tar.bz2"

    def test_tar_bz2_case_insensitive(self):
        assert get_format("ARCHIVE.TAR.BZ2") == ".tar.bz2"

    def test_tar_xz_case_insensitive(self):
        assert get_format("ARCHIVE.TAR.XZ") == ".tar.xz"

    def test_all_supported_formats_recognized(self):
        """Every format in SUPPORTED_FORMATS should be detected by get_format."""
        for ext in SUPPORTED_FORMATS:
            assert get_format(f"pkg{ext}") is not None, f"{ext} not recognised"


# =============================================================================
# _get_package_from_request — URL failures
# =============================================================================


class TestGetPackageFromRequestUrlFailures:
    @pytest.mark.asyncio
    async def test_url_download_http_error_returns_error(self):
        """When the URL returns an HTTP error, the endpoint should return 500."""
        with patch("app2nix.server.httpx.AsyncClient") as mock_httpx_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_cls.return_value = mock_client

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
    async def test_url_download_connection_error_returns_500(self):
        """When the URL is unreachable, the endpoint should return 500."""
        with patch("app2nix.server.httpx.AsyncClient") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_cls.return_value = mock_client

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    data={"url": "https://unreachable.example.com/pkg.deb"},
                )

        assert r.status_code == 500
        assert "Analysis failed" in r.json()["error"]


# =============================================================================
# Upload size — boundary tests
# =============================================================================


class TestUploadSizeBoundary:
    @pytest.mark.asyncio
    async def test_file_exactly_at_limit_succeeds(self):
        """A file exactly at max_upload_size should be accepted."""
        from app2nix.config import settings
        original = settings.max_upload_size
        settings.max_upload_size = 1024  # 1 KB limit
        try:
            exact_content = b"0" * 1024  # exactly 1 KB
            with patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = PackageInfo(
                    name="test", version="1.0", format="deb"
                )
                mock_analyzer_cls.return_value = mock_analyzer
                with patch("app2nix.server.DependencyResolver") as mock_resolver_cls:
                    mock_resolver = MagicMock()
                    mock_resolver.resolve_all.return_value = ([], [])
                    mock_resolver_cls.return_value = mock_resolver

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        r = await client.post(
                            "/analyze",
                            files={"file": ("test.deb", exact_content, "application/octet-stream")},
                        )
            assert r.status_code == 200
        finally:
            settings.max_upload_size = original

    @pytest.mark.asyncio
    async def test_file_one_byte_over_limit_returns_413(self):
        """A file one byte over max_upload_size should be rejected."""
        from app2nix.config import settings
        original = settings.max_upload_size
        settings.max_upload_size = 1024
        try:
            oversized = b"0" * 1025  # 1 byte over limit
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("big.deb", oversized, "application/octet-stream")},
                )
            assert r.status_code == 413
            assert "too large" in r.json()["error"]
        finally:
            settings.max_upload_size = original

    @pytest.mark.asyncio
    async def test_file_one_byte_under_limit_succeeds(self):
        """A file one byte under max_upload_size should be accepted."""
        from app2nix.config import settings
        original = settings.max_upload_size
        settings.max_upload_size = 1024
        try:
            under_content = b"0" * 1023
            with patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = PackageInfo(
                    name="test", version="1.0", format="deb"
                )
                mock_analyzer_cls.return_value = mock_analyzer
                with patch("app2nix.server.DependencyResolver") as mock_resolver_cls:
                    mock_resolver = MagicMock()
                    mock_resolver.resolve_all.return_value = ([], [])
                    mock_resolver_cls.return_value = mock_resolver

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        r = await client.post(
                            "/analyze",
                            files={"file": ("test.deb", under_content, "application/octet-stream")},
                        )
            assert r.status_code == 200
        finally:
            settings.max_upload_size = original

    @pytest.mark.asyncio
    async def test_empty_file_with_valid_format_accepted(self):
        """An empty file with a valid extension should be accepted by the format check."""
        with patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="empty", version="1.0", format="deb"
            )
            mock_analyzer_cls.return_value = mock_analyzer
            with patch("app2nix.server.DependencyResolver") as mock_resolver_cls:
                mock_resolver = MagicMock()
                mock_resolver.resolve_all.return_value = ([], [])
                mock_resolver_cls.return_value = mock_resolver

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    r = await client.post(
                        "/analyze",
                        files={"file": ("empty.deb", b"", "application/octet-stream")},
                    )
        assert r.status_code == 200


# =============================================================================
# Both file and URL — URL takes precedence
# =============================================================================


class TestFileAndUrlPrecedence:
    @pytest.mark.asyncio
    async def test_url_takes_precedence_over_file(self):
        """When both url and file are provided, the URL should be used."""
        with (
            patch("app2nix.server.httpx.AsyncClient") as mock_httpx_cls,
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
        ):
            mock_resp = MagicMock()
            mock_resp.content = b"url-content"
            mock_resp.raise_for_status = MagicMock()
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_cls.return_value = mock_client

            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="url-pkg", version="1.0", format="deb"
            )
            mock_analyzer_cls.return_value = mock_analyzer
            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = ([], [])
            mock_resolver_cls.return_value = mock_resolver

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    data={"url": "https://example.com/pkg.deb"},
                    files={"file": ("local.deb", b"local-content", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "url-pkg"


# =============================================================================
# Generate with unresolved dependencies
# =============================================================================


class TestGenerateWithUnresolvedDeps:
    @pytest.mark.asyncio
    async def test_generate_reports_unresolved_deps(self):
        """When some deps can't be resolved, they should appear in unresolved_deps."""
        with (
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
            patch("app2nix.server.NixGenerator") as mock_generator_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="mixed", version="1.0", format="deb",
                dependencies=["ssl", "unknown_xyz"]
            )
            mock_analyzer_cls.return_value = mock_analyzer

            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = (
                ["openssl"],
                ["unknown_xyz"],
            )
            mock_resolver_cls.return_value = mock_resolver

            mock_generator = MagicMock()
            mock_result = MagicMock()
            mock_result.nix_content = "nix content"
            mock_result.flake_content = None
            mock_result.install_guide = ""
            mock_result.install_script = ""
            mock_result.validation_passed = True
            mock_generator.generate_default_nix.return_value = mock_result
            mock_generator_cls.return_value = mock_generator

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={"file": ("mixed.deb", b"data", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert "unknown_xyz" in data["unresolved_deps"]
        assert "openssl" in data["unresolved_deps"] or len(data["unresolved_deps"]) == 1


# =============================================================================
# Temp file cleanup verification
# =============================================================================


class TestTempFileCleanup:
    @pytest.mark.asyncio
    async def test_analyze_cleans_up_temp_dir_on_success(self):
        """Temp directory should be cleaned up after successful analysis."""
        temp_dirs = []

        original_mkdtemp = __import__("tempfile").mkdtemp

        def tracking_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            temp_dirs.append(d)
            return d

        with (
            patch("app2nix.server.tempfile.mkdtemp", side_effect=tracking_mkdtemp),
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
            patch("app2nix.server.DependencyResolver") as mock_resolver_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = PackageInfo(
                name="cleanup-test", version="1.0", format="deb"
            )
            mock_analyzer_cls.return_value = mock_analyzer
            mock_resolver = MagicMock()
            mock_resolver.resolve_all.return_value = ([], [])
            mock_resolver_cls.return_value = mock_resolver

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("cleanup.deb", b"data", "application/octet-stream")},
                )

        assert r.status_code == 200
        # All temp dirs created during the request should be cleaned up
        for d in temp_dirs:
            assert not Path(d).exists(), f"Temp dir {d} was not cleaned up"

    @pytest.mark.asyncio
    async def test_analyze_cleans_up_temp_dir_on_error(self):
        """Temp directory should be cleaned up even when analysis fails."""
        temp_dirs = []

        original_mkdtemp = __import__("tempfile").mkdtemp

        def tracking_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            temp_dirs.append(d)
            return d

        with (
            patch("app2nix.server.tempfile.mkdtemp", side_effect=tracking_mkdtemp),
            patch("app2nix.server.UniversalAnalyzer") as mock_analyzer_cls,
        ):
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.side_effect = RuntimeError("analysis exploded")
            mock_analyzer_cls.return_value = mock_analyzer

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("error.deb", b"data", "application/octet-stream")},
                )

        assert r.status_code == 500
        for d in temp_dirs:
            assert not Path(d).exists(), f"Temp dir {d} was not cleaned up on error"
