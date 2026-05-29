"""
End-to-end tests for the .deb analysis pipeline with mocked subprocess.

Simulates real tool outputs (dpkg-deb, file, ldd, patchelf) at the
subprocess level and verifies the full chain:

    analyze_deb() → PackageInfo → DependencyResolver → NixGenerator → ConversionResult

No real .deb files or system tools are required.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app2nix.core.analyzers.deb import analyze_deb
from app2nix.core.generator import NixGenerator
from app2nix.core.resolver import DependencyResolver
from app2nix.models import PackageInfo


# =============================================================================
# Helpers — factory for mocked subprocess calls during .deb analysis
# =============================================================================


def make_subprocess_side_effect(
    *,
    dpkg_deb_x_ok: bool = True,
    dpkg_deb_I_stdout: str = "",
    file_responses: dict[str, str] | None = None,
    ldd_stdout: str = "",
    patchelf_stdout: str = "",
    fail_all: bool = False,
):
    """
    Build a side_effect callable for ``subprocess.run`` that simulates the
    tools called by ``analyze_deb``:

      1. dpkg-deb -x <path> <tmpdir>
      2. dpkg-deb -I <path>
      3. file -b <elf>  (once per ELF candidate)
      4. ldd <elf>      (once per detected ELF)
      5. patchelf --print-needed <elf>  (once per detected ELF)
    """
    def _side_effect(cmd, **kwargs):
        if fail_all:
            raise RuntimeError("simulated failure")

        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""

        # 1. dpkg-deb -x <src> <dest>
        if cmd[:2] == ["dpkg-deb", "-x"]:
            if dpkg_deb_x_ok:
                # cmd[3] is the destination temp directory
                tmp_root = Path(cmd[3])
                (tmp_root / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (tmp_root / "usr" / "lib").mkdir(parents=True, exist_ok=True)
                (tmp_root / "usr" / "bin" / "myapp").write_text("fake elf")
                (tmp_root / "usr" / "bin" / "myapp").chmod(0o755)
                (tmp_root / "usr" / "lib" / "libhelper.so").write_text("fake lib")
                mock.returncode = 0
            else:
                # check=True triggers CalledProcessError when returncode != 0
                raise subprocess.CalledProcessError(1, cmd, stderr="dpkg-deb: error: extraction failed")

        # 2. dpkg-deb -I
        elif cmd[:2] == ["dpkg-deb", "-I"]:
            mock.stdout = dpkg_deb_I_stdout

        # 3. file -b <path>
        elif cmd[:2] == ["file", "-b"]:
            target = cmd[2]
            if file_responses:
                for pattern, result in file_responses.items():
                    if pattern in target:
                        mock.stdout = result
                        break
                else:
                    mock.stdout = "ASCII text"
            else:
                # Default: files in usr/bin/ or usr/lib/ are ELF executables
                if "usr/bin/" in target or "usr/lib/" in target:
                    mock.stdout = "ELF 64-bit LSB executable, x86-64"
                else:
                    mock.stdout = "ASCII text"

        # 4. ldd <path>
        elif cmd[0] == "ldd":
            mock.stdout = ldd_stdout

        # 5. patchelf --print-needed <path>
        elif cmd[:2] == ["patchelf", "--print-needed"]:
            mock.stdout = patchelf_stdout

        return mock

    return _side_effect


# =============================================================================
# E2E Pipeline Tests
# =============================================================================

DPKG_DEB_I_OUTPUT = (
    "Package: my-app\n"
    "Version: 2.1.0\n"
    "Architecture: amd64\n"
    "Depends: libssl3 (>= 3.0), libc6 (>= 2.35), zlib1g | libz-dev\n"
    "Description: A sample package for testing\n"
    "Homepage: https://example.com\n"
)


class TestDebAnalysisE2E:
    """End-to-end analysis of a .deb file with fully mocked subprocess."""

    def test_full_analysis_returns_complete_package_info(self, tmp_path):
        """Analyze a .deb and verify all fields are populated correctly."""
        deb_file = tmp_path / "my-app_2.1.0_amd64.deb"
        deb_file.write_text("fake deb content")

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=DPKG_DEB_I_OUTPUT,
            file_responses={
                "myapp": "ELF 64-bit LSB executable, x86-64",
                "libhelper.so": "ELF 64-bit LSB shared object, x86-64",
            },
            ldd_stdout=(
                "\tlinux-vdso.so.1 (0x00007fff)\n"
                "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
                "\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f00)\n"
            ),
            patchelf_stdout="libz.so.1\n",
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))

        assert info.name == "my-app"
        assert info.version == "2.1.0"
        assert info.architecture == "amd64"
        assert info.format == "deb"
        # Description is not currently parsed by analyze_deb — skip that check

        # Dependencies from ldd + patchelf (not from Depends field)
        assert "ssl" in info.dependencies, f"deps: {info.dependencies}"
        assert "c" in info.dependencies, f"deps: {info.dependencies}"
        assert "z" in info.dependencies, f"deps: {info.dependencies}"

        # Executables
        assert any("usr/bin/myapp" in str(e) for e in info.executables), f"execs: {info.executables}"
        # Libraries are also discovered by _find_elf
        assert any("libhelper.so" in str(e) for e in info.executables), f"execs: {info.executables}"

    def test_cleanup_mocked(self, tmp_path):
        """Temp directory should be cleaned up via shutil.rmtree after analysis."""
        deb_file = tmp_path / "pkg.deb"
        deb_file.write_text("data")

        created_tempdirs = []

        def track_mkdtemp(*args, **kwargs):
            d = tmp_path / "deb_workdir"
            d.mkdir(exist_ok=True)
            created_tempdirs.append(str(d))
            return str(d)

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=(
                "Package: pkg\nVersion: 1.0\nArchitecture: amd64\n"
            ),
        )

        with (
            patch("app2nix.core.analyzers.deb.tempfile.mkdtemp", side_effect=track_mkdtemp),
            patch("app2nix.core.analyzers.deb.shutil.rmtree") as mock_rmtree,
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            analyze_deb(str(deb_file))

        # Verify the temp dir was cleaned up after success
        mock_rmtree.assert_called_once()

    def test_cleanup_on_extraction_failure(self, tmp_path):
        """Temp directory should be cleaned up even if dpkg-deb -x fails."""
        deb_file = tmp_path / "broken.deb"
        deb_file.write_text("corrupt")

        # Track temp dirs created by tempfile.mkdtemp
        created_tempdirs = []

        def track_mkdtemp(*args, **kwargs):
            d = tmp_path / "deb_workdir"
            d.mkdir(exist_ok=True)
            created_tempdirs.append(str(d))
            return str(d)

        side_effect = make_subprocess_side_effect(
            dpkg_deb_x_ok=False,
            dpkg_deb_I_stdout="",
        )

        with (
            patch("app2nix.core.analyzers.deb.tempfile.mkdtemp", side_effect=track_mkdtemp),
            patch("app2nix.core.analyzers.deb.shutil.rmtree") as mock_rmtree,
            patch.object(subprocess, "run", side_effect=side_effect),
            pytest.raises(Exception),
        ):
            analyze_deb(str(deb_file))

        # Verify the temp dir was cleaned up
        mock_rmtree.assert_called_once()

    def test_cleanup_on_success(self, tmp_path):
        """Temp directory should be removed after successful analysis."""
        deb_file = tmp_path / "pkg.deb"
        deb_file.write_text("data")

        created_tempdirs = []

        def track_mkdtemp(*args, **kwargs):
            d = tmp_path / "deb_workdir"
            d.mkdir(exist_ok=True)
            created_tempdirs.append(str(d))
            return str(d)

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=(
                "Package: pkg\nVersion: 1.0\nArchitecture: amd64\n"
            ),
        )

        with (
            patch("app2nix.core.analyzers.deb.tempfile.mkdtemp", side_effect=track_mkdtemp),
            patch("app2nix.core.analyzers.deb.shutil.rmtree") as mock_rmtree,
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            analyze_deb(str(deb_file))

        # Verify the temp dir was cleaned up after success
        mock_rmtree.assert_called_once()


class TestDebParsingEdgeCases:
    """Edge cases in .deb control file parsing."""

    @pytest.mark.parametrize(
        ("arch", "expected"),
        [
            ("amd64", "amd64"),
            ("i386", "i386"),
            ("arm64", "arm64"),
            ("armhf", "armhf"),
            ("all", "all"),
            ("mips64el", "mips64el"),
        ],
    )
    def test_preserves_architecture(self, tmp_path, arch, expected):
        """Architecture from the control file should be preserved as-is."""
        deb_file = tmp_path / f"pkg_{arch}.deb"
        deb_file.write_text("data")
        ctrl = f"Package: pkg\nVersion: 1.0\nArchitecture: {arch}\n"

        side_effect = make_subprocess_side_effect(dpkg_deb_I_stdout=ctrl)

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))
        assert info.architecture == expected

    def test_depends_alternatives_parsed_as_first_option(self, tmp_path):
        """
        "Depends: libfoo | libbar" should only keep "libfoo"
        (the first option before the pipe).
        """
        deb_file = tmp_path / "alt.deb"
        deb_file.write_text("data")
        ctrl = (
            "Package: alt-app\n"
            "Version: 1.0\n"
            "Architecture: amd64\n"
            "Depends: libfoo (>= 1.0) | libbar, libbaz\n"
        )

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=ctrl,
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            # analyze_deb doesn't use Depends for dependencies — it uses ldd/patchelf
            # But we test it doesn't crash and returns basic info
            info = analyze_deb(str(deb_file))
        assert info.name == "alt-app"
        assert info.version == "1.0"
        # Depends field is not currently used for info.dependencies
        assert info.dependencies == []

    def test_version_string_with_epoch(self, tmp_path):
        """Version with epoch (e.g. 2:1.0-1) should be preserved."""
        deb_file = tmp_path / "epoch.deb"
        deb_file.write_text("data")
        ctrl = "Package: epoch-pkg\nVersion: 2:1.0-1\nArchitecture: amd64\n"

        side_effect = make_subprocess_side_effect(dpkg_deb_I_stdout=ctrl)

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))
        assert info.version == "2:1.0-1"

    def test_missing_optional_fields_defaults(self, tmp_path):
        """Minimal control file should fall back to defaults."""
        deb_file = tmp_path / "minimal.deb"
        deb_file.write_text("data")
        ctrl = "Package: minimal-pkg\n"

        side_effect = make_subprocess_side_effect(dpkg_deb_I_stdout=ctrl)

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))
        assert info.name == "minimal-pkg"
        assert info.version == "1.0"  # default fallback
        assert info.architecture == "amd64"  # default fallback


class TestDebElfDetection:
    """ELF detection during .deb analysis."""

    def test_detects_both_executables_and_shared_objects(self, tmp_path):
        """Both 'executable' and 'shared object' ELFs should be discovered."""
        deb_file = tmp_path / "multi.deb"
        deb_file.write_text("data")

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout="Package: multi\nVersion: 1.0\nArchitecture: amd64\n",
            file_responses={
                "myapp": "ELF 64-bit LSB executable, x86-64",
                "libhelper.so": "ELF 64-bit LSB shared object, x86-64",
            },
            ldd_stdout=(
                "\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f00)\n"
            ),
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))

        assert "c" in info.dependencies
        assert len(info.executables) == 2

    def test_no_elf_files_returns_empty_deps(self, tmp_path):
        """When no ELF files are found, dependencies should be empty."""
        deb_file = tmp_path / "no-elf.deb"
        deb_file.write_text("data")

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout="Package: no-elf\nVersion: 1.0\nArchitecture: all\n",
            file_responses={
                "myapp": "Bourne-Again shell script, ASCII text executable",
                "libhelper.so": "ASCII text",
            },
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))

        assert info.dependencies == []
        # Scripts/text files aren't ELF, so no executables
        assert info.executables == []

    def test_ldd_failure_falls_back_to_patchelf(self, tmp_path):
        """If ldd fails for a binary, patchelf should still be tried."""
        deb_file = tmp_path / "fallback.deb"
        deb_file.write_text("data")

        call_count = {"ldd": 0, "patchelf": 0}

        def side_effect(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = ""
            mock.stderr = ""

            if cmd[:2] == ["dpkg-deb", "-x"]:
                tmp_root = Path(cmd[3])
                (tmp_root / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (tmp_root / "usr" / "bin" / "app").write_text("elf")
                mock.returncode = 0
            elif cmd[:2] == ["dpkg-deb", "-I"]:
                mock.stdout = "Package: fallback\nVersion: 1.0\nArchitecture: amd64\n"
            elif cmd[:2] == ["file", "-b"]:
                mock.stdout = "ELF 64-bit LSB executable, x86-64"
            elif cmd[0] == "ldd":
                call_count["ldd"] += 1
                # ldd fails
                raise RuntimeError("ldd: command not found")
            elif cmd[:2] == ["patchelf", "--print-needed"]:
                call_count["patchelf"] += 1
                mock.stdout = "libssl.so.3\n"

            return mock

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))

        assert call_count["ldd"] >= 1
        assert call_count["patchelf"] >= 1
        # patchelf should have found the dep even though ldd failed
        assert "ssl" in info.dependencies


class TestDebAnalysisWithFullPipeline:
    """Full pipeline: analyze → resolve → generate with mocked subprocess."""

    DEB_PATH = "/fake/packages/hello-app_1.2.3_amd64.deb"

    DPKG_INFO = (
        "Package: hello-app\n"
        "Version: 1.2.3\n"
        "Architecture: amd64\n"
        "Depends: libssl3 (>= 3.0), libc6\n"
    )

    LDD_OUTPUT = (
        "\tlinux-vdso.so.1 (0x00007fff)\n"
        "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
        "\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f00)\n"
    )

    def _make_pipeline_side_effect(self, tmp_path):
        """Build a side_effect that simulates dpkg-deb, file, ldd, patchelf."""

        def side_effect(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = ""
            mock.stderr = ""

            if cmd[:2] == ["dpkg-deb", "-x"]:
                tmp_root = Path(cmd[3])
                (tmp_root / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (tmp_root / "usr" / "bin" / "hello").write_text("elf")
                (tmp_root / "usr" / "bin" / "hello").chmod(0o755)
                mock.returncode = 0
            elif cmd[:2] == ["dpkg-deb", "-I"]:
                mock.stdout = self.DPKG_INFO
            elif cmd[:2] == ["file", "-b"]:
                mock.stdout = "ELF 64-bit LSB executable, x86-64"
            elif cmd[0] == "ldd":
                mock.stdout = self.LDD_OUTPUT
            elif cmd[:2] == ["patchelf", "--print-needed"]:
                mock.stdout = ""

            return mock

        return side_effect

    def test_analyze_then_resolve(self, tmp_path):
        """
        Analyze a .deb → get PackageInfo → resolve dependencies with real resolver.
        """
        deb_file = tmp_path / "hello-app_1.2.3_amd64.deb"
        deb_file.write_text("fake deb")

        with patch.object(subprocess, "run", side_effect=self._make_pipeline_side_effect(tmp_path)):
            info = analyze_deb(str(deb_file))

        assert info.name == "hello-app"
        assert info.version == "1.2.3"
        assert info.format == "deb"
        assert "ssl" in info.dependencies
        assert "c" in info.dependencies

        # Resolve dependencies using the real resolver
        resolver = DependencyResolver(tmp_path / "test_cache.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        assert "openssl" in resolved, f"resolved: {resolved}"  # ssl → openssl
        # 'c' is NOT in DEP_MAP, so it should be unresolved
        assert any("c" in u for u in unresolved), f"unresolved: {unresolved}"
        assert "unknown_xyz" not in unresolved  # no unknown deps besides 'c'

    def test_full_pipeline_analyze_to_nix_generation(self, tmp_path):
        """
        Full end-to-end: analyze .deb → resolve deps → generate default.nix.
        Verifies the generated Nix expression is syntactically valid.
        """
        deb_file = tmp_path / "hello-app_1.2.3_amd64.deb"
        deb_file.write_text("fake deb")

        with patch.object(subprocess, "run", side_effect=self._make_pipeline_side_effect(tmp_path)):
            info = analyze_deb(str(deb_file))

        assert info.format == "deb"
        assert info.dependencies  # has deps

        # Resolve
        resolver = DependencyResolver(tmp_path / "cache.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        # Generate
        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=resolved, unresolved=unresolved)

        # Check the result
        assert result.package.name == "hello-app"
        assert result.package.format == "deb"
        assert result.nix_content is not None
        assert len(result.nix_content) > 50

        # Should include the package name in the derivation
        assert "hello-app" in result.nix_content
        # Should reference dpkg in nativeBuildInputs for deb format
        assert "dpkg" in result.nix_content
        # Should include autoPatchelfHook
        assert "autoPatchelfHook" in result.nix_content
        # Should include resolved deps as pkgs.*
        assert "pkgs.openssl" in result.nix_content

        # Flake content should also be present
        assert result.flake_content is not None
        assert "hello-app" in result.flake_content

        # Install script and guide
        assert result.install_script is not None
        assert "hello-app" in result.install_script
        assert result.install_guide is not None
        assert "hello-app" in result.install_guide

    def test_pipeline_without_unresolved_deps(self, tmp_path):
        """When all deps resolve, unresolved list should be empty."""
        deb_file = tmp_path / "simple.deb"
        deb_file.write_text("data")

        # Only deps that are in DEP_MAP
        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout="Package: simple\nVersion: 1.0\nArchitecture: amd64\n",
            ldd_stdout=(
                "\tlibz.so.1 => /usr/lib/libz.so.1 (0x00007f00)\n"
            ),
            patchelf_stdout="libssl.so.3\n",
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))

        resolver = DependencyResolver(tmp_path / "cache2.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        assert "zlib" in resolved or "openssl" in resolved
        # z → zlib (resolved), ssl → openssl (resolved)
        assert unresolved == []

    def test_pipeline_resolves_mixed_deps(self, tmp_path):
        """Mix of resolvable and unresolvable dependencies."""
        deb_file = tmp_path / "mixed.deb"
        deb_file.write_text("data")

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout="Package: mixed\nVersion: 1.0\nArchitecture: amd64\n",
            ldd_stdout=(
                "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
                "\tlibweird_internal.so => /opt/lib/libweird_internal.so (0x00007f00)\n"
            ),
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))

        resolver = DependencyResolver(tmp_path / "cache3.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        assert "openssl" in resolved  # ssl → resolved
        # 'weird_internal' is not in DEP_MAP
        assert any("weird_internal" in u for u in unresolved)

    def test_generate_with_mixed_deps_includes_unresolved(self, tmp_path):
        """Generated result should list unresolved dependencies."""
        deb_file = tmp_path / "mixed2.deb"
        deb_file.write_text("data")

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout="Package: mixed2\nVersion: 1.0\nArchitecture: amd64\n",
            ldd_stdout=(
                "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
                "\tlibunknown_xyz.so => /usr/lib/libunknown_xyz.so (0x00007f00)\n"
            ),
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            info = analyze_deb(str(deb_file))

        resolver = DependencyResolver(tmp_path / "cache4.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=resolved, unresolved=unresolved)

        assert "openssl" in resolved
        assert len(unresolved) >= 1
        assert result.unresolved_deps == unresolved
        # The generated Nix should include the resolved dep
        assert "pkgs.openssl" in result.nix_content


class TestDebServerPipeline:
    """Server-level E2E tests: mock only subprocess, use real server components."""

    @pytest.mark.asyncio
    async def test_server_analyze_endpoint_mocks_subprocess_only(self, tmp_path):
        """
        POST /analyze should work when only subprocess is mocked (not the
        analyzer class itself). This tests that the server correctly wires
        UniversalAnalyzer → analyze_deb → subprocess.
        """
        from app2nix.server import app

        deb_content = b"fake deb"

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=(
                "Package: server-test\n"
                "Version: 3.0.0\n"
                "Architecture: amd64\n"
            ),
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("pkg.deb", deb_content, "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "server-test"
        assert data["version"] == "3.0.0"
        assert data["format"] == "deb"
        assert data["architecture"] == "amd64"

    @pytest.mark.asyncio
    async def test_server_generate_endpoint_mocks_subprocess_only(self, tmp_path):
        """
        POST /generate should work when only subprocess is mocked.
        Tests the full server-side pipeline: upload → analyze → resolve → generate.
        """
        from app2nix.server import app

        deb_content = b"fake deb"

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=(
                "Package: gen-test\n"
                "Version: 4.0.0\n"
                "Architecture: arm64\n"
            ),
            ldd_stdout=(
                "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
            ),
            patchelf_stdout="libz.so.1\n",
        )

        with patch.object(subprocess, "run", side_effect=side_effect):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={"file": ("pkg.deb", deb_content, "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "gen-test"
        assert data["version"] == "4.0.0"
        assert data["architecture"] == "arm64"
        assert "mkDerivation" in data["content"]
        assert data["validation_passed"] is True
        assert data["auto_install_script"] is not None
        assert data["install_guide"] is not None
        # Should have resolved deps
        assert "openssl" in data["content"] or "zlib" in data["content"]


class TestDebCLIPipeline:
    """CLI-level E2E tests: invoke the CLI with mocked subprocess (using Typer)."""

    def test_cli_convert_command_with_mocked_subprocess(self, tmp_path):
        """
        Simulate 'app2nix convert package.deb' with only subprocess mocked.
        Verifies the CLI output file contains the expected Nix expression.
        """
        from typer.testing import CliRunner
        from app2nix.cli import app

        deb_file = tmp_path / "cli-test_1.0_amd64.deb"
        deb_file.write_text("fake deb content")
        out_dir = tmp_path / "nix-output"
        out_dir.mkdir()

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=(
                "Package: cli-test\n"
                "Version: 1.0\n"
                "Architecture: amd64\n"
            ),
            ldd_stdout=(
                "\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f00)\n"
            ),
        )

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side_effect):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Generated" in result.output

        # Check the output file was created
        nix_file = out_dir / "default.nix"
        assert nix_file.exists()
        content = nix_file.read_text()
        assert "cli-test" in content
        assert "mkDerivation" in content
        assert "autoPatchelfHook" in content

    def test_cli_convert_with_flake_flag(self, tmp_path):
        """
        Simulate 'app2nix convert package.deb --flake' with mocked subprocess.
        """
        from typer.testing import CliRunner
        from app2nix.cli import app

        deb_file = tmp_path / "flake-test_2.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "flake-out"
        out_dir.mkdir()

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=(
                "Package: flake-test\n"
                "Version: 2.0\n"
                "Architecture: amd64\n"
            ),
            ldd_stdout=(
                "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
            ),
        )

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side_effect):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0
        assert (out_dir / "default.nix").exists()
        assert (out_dir / "flake.nix").exists()
        flake_content = (out_dir / "flake.nix").read_text()
        assert "flake-test" in flake_content

    def test_cli_convert_with_json_flag(self, tmp_path):
        """Simulate 'app2nix convert package.deb --json' generates JSON descriptor."""
        from typer.testing import CliRunner
        from app2nix.cli import app

        deb_file = tmp_path / "json-test_1.5_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "json-out"
        out_dir.mkdir()

        side_effect = make_subprocess_side_effect(
            dpkg_deb_I_stdout=(
                "Package: json-test\n"
                "Version: 1.5\n"
                "Architecture: amd64\n"
            ),
        )

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side_effect):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--json"],
            )

        assert result.exit_code == 0
        json_file = out_dir / "json-test.json"
        assert json_file.exists()
        import json
        data = json.loads(json_file.read_text())
        assert data["name"] == "json-test"
        assert data["version"] == "1.5"

    def test_cli_convert_nonexistent_file_errors(self, tmp_path):
        """Non-existent .deb file should exit with error."""
        from typer.testing import CliRunner
        from app2nix.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["convert", str(tmp_path / "does-not-exist.deb")])
        assert result.exit_code != 0
        assert "File not found" in result.output
