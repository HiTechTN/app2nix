"""
End-to-end tests for all non-.deb analyzers (AppImage, Snap, RPM, Flatpak, Tarball)
with mocked subprocess.

Each format has its own subprocess call pattern, simulated via side_effect
factories.  Tests cover:

    analyze_<fmt>() → PackageInfo → DependencyResolver → NixGenerator → ConversionResult

No real package files or system tools are required.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app2nix.core.analyzers.appimage import analyze_appimage
from app2nix.core.analyzers.flatpak import analyze_flatpak
from app2nix.core.analyzers.rpm import analyze_rpm
from app2nix.core.analyzers.snap import analyze_snap
from app2nix.core.analyzers.tarball import analyze_tarball
from app2nix.core.generator import NixGenerator
from app2nix.core.resolver import DependencyResolver
from app2nix.models import PackageInfo

# =============================================================================
# Helpers — shared mock utilities
# =============================================================================


def _make_elf_mock(stdout: str) -> MagicMock:
    """Return a MagicMock that looks like a subprocess.run result for ELF tools."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


def _make_file_patchelf_side_effect(
    elf_files: tuple[str, ...] = ("myapp", "libhelper.so"),
    patchelf_output: str = "libssl.so.3\nlibc.so.6\n",
    non_elf_response: str = "ASCII text",
) -> callable:
    """
    Build a side_effect for ``subprocess.run`` that handles ``file -b <path>``
    and ``patchelf --print-needed <path>`` — used by both AppImage and Tarball
    analyzers.
    """
    def _side_effect(cmd, **kwargs):
        if cmd[:2] == ["file", "-b"]:
            target = cmd[2]
            if any(e in target for e in elf_files):
                return _make_elf_mock("ELF 64-bit LSB executable, x86-64")
            return _make_elf_mock(non_elf_response)
        if cmd[:2] == ["patchelf", "--print-needed"]:
            return _make_elf_mock(patchelf_output)
        # fall through — caller must handle other commands
        return None
    return _side_effect


# =============================================================================
# AppImage
# =============================================================================


def make_appimage_side_effect(
    fuse_succeeds: bool = True,
    unsquashfs_succeeds: bool = True,
    elf_files: tuple[str, ...] = ("myapp", "libhelper.so"),
    patchelf_output: str = "libssl.so.3\nlibc.so.6\n",
    fail_all: bool = False,
) -> callable:
    """
    Build a side_effect for ``subprocess.run`` that simulates the tools
    called by ``analyze_appimage``:

      1. ``[<appimage>, \"--appimage-extract\"]`` (FUSE)
      2. ``[\"unsquashfs\", \"-d\", <dest>, <appimage>]``   (fallback)
      3. ``[\"file\", \"-b\", <f>]``                         (per file)
      4. ``[\"patchelf\", \"--print-needed\", <f>]``         (per ELF)
    """
    elf_side = _make_file_patchelf_side_effect(elf_files, patchelf_output)

    def _side_effect(cmd, **kwargs):
        if fail_all:
            raise RuntimeError("simulated failure")

        # 1. AppImage --appimage-extract  (FUSE)
        if len(cmd) == 2 and cmd[1] == "--appimage-extract":
            cwd = kwargs.get("cwd", Path.cwd())
            sf = Path(cwd) / "squashfs-root"
            if fuse_succeeds:
                sf.mkdir(parents=True, exist_ok=True)
                (sf / "usr").mkdir(exist_ok=True)
                (sf / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (sf / "usr" / "bin" / "myapp").write_text("elf")
                (sf / "usr" / "bin" / "myapp").chmod(0o755)
                (sf / "usr" / "lib").mkdir(parents=True, exist_ok=True)
                (sf / "usr" / "lib" / "libhelper.so").write_text("elf")
                return _make_elf_mock("")
            return _make_elf_mock("FUSE extraction not supported")

        # 2. unsquashfs -d <dest> <appimage> [-o <offset>]
        if cmd[0] == "unsquashfs" and "-d" in cmd:
            dest_idx = cmd.index("-d") + 1
            dest = Path(cmd[dest_idx])
            if unsquashfs_succeeds:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "usr").mkdir(exist_ok=True)
                (dest / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (dest / "usr" / "bin" / "myapp").write_text("elf")
                (dest / "usr" / "bin" / "myapp").chmod(0o755)
                return _make_elf_mock("")
            return _make_elf_mock("unsquashfs failed")

        # 3. file -b / patchelf --print-needed
        result = elf_side(cmd, **kwargs)
        if result is not None:
            return result

        return _make_elf_mock("")

    return _side_effect


class TestAppImageE2E:
    """E2E tests for AppImage analysis with mocked subprocess."""

    def test_full_analysis_returns_complete_info(self, tmp_path):
        """Analyze an AppImage and verify all fields are populated."""
        ai_path = tmp_path / "MyApp-1.0.AppImage"
        ai_path.write_text("fake appimage")
        ai_path.chmod(0o755)

        side_effect = make_appimage_side_effect(
            fuse_succeeds=True,
            patchelf_output="libssl.so.3\nlibc.so.6\nlibz.so.1\n",
        )

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            info = analyze_appimage(str(ai_path))

        assert info.name == "myapp-1.0"  # lowercased by sanitize_name
        assert info.version == "1.0"
        assert info.architecture == "x86_64"
        assert info.format == "appimage"
        assert "ssl" in info.dependencies
        assert "c" in info.dependencies
        assert "z" in info.dependencies
        assert any("usr/bin/myapp" in e for e in info.executables)

    def test_fallback_to_unsquashfs_when_fuse_fails(self, tmp_path):
        """When FUSE extraction fails, fall back to unsquashfs."""
        ai_path = tmp_path / "fallback.AppImage"
        # Must be large enough for _appimage_offset to seek -8 bytes
        ai_path.write_bytes(b"x" * 100 + b"     12345")
        ai_path.chmod(0o755)

        side_effect = make_appimage_side_effect(
            fuse_succeeds=False,
            unsquashfs_succeeds=True,
            patchelf_output="libssl.so.3\n",
        )

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            info = analyze_appimage(str(ai_path))

        assert info.format == "appimage"
        assert "ssl" in info.dependencies

    def test_raises_when_both_extraction_methods_fail(self, tmp_path):
        """When both FUSE and unsquashfs fail, raise ValueError."""
        ai_path = tmp_path / "broken.AppImage"
        # Must be large enough for _appimage_offset to seek -8 bytes
        ai_path.write_bytes(b"x" * 100 + b"     12345")

        side_effect = make_appimage_side_effect(
            fuse_succeeds=False,
            unsquashfs_succeeds=False,
        )

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
            pytest.raises(ValueError, match="Failed to extract AppImage"),
        ):
            analyze_appimage(str(ai_path))

    def test_raises_when_unsquashfs_missing(self, tmp_path):
        """When unsquashfs is not installed, raise ValueError early."""
        ai_path = tmp_path / "no-tools.AppImage"
        ai_path.write_text("fake")

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value=None),
            pytest.raises(ValueError, match="unsquashfs"),
        ):
            analyze_appimage(str(ai_path))

    def test_no_elf_files_returns_empty_deps(self, tmp_path):
        """With no ELF files inside, dependencies should be empty."""
        ai_path = tmp_path / "script.AppImage"
        ai_path.write_text("fake")
        ai_path.chmod(0o755)

        side_effect = make_appimage_side_effect(
            fuse_succeeds=True,
            elf_files=("",),  # no ELF files
            patchelf_output="",
        )

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            info = analyze_appimage(str(ai_path))

        assert info.dependencies == []

    def test_cleanup_on_success(self, tmp_path):
        """Temp directory should be cleaned up after successful AppImage analysis."""
        ai_path = tmp_path / "cleanup-test.AppImage"
        ai_path.write_text("fake")
        ai_path.chmod(0o755)

        def track_mkdtemp(*args, **kwargs):
            d = tmp_path / "ai_workdir"
            d.mkdir(exist_ok=True)
            return str(d)

        side_effect = make_appimage_side_effect(fuse_succeeds=True)

        with (
            patch("app2nix.core.analyzers.appimage.tempfile.mkdtemp", side_effect=track_mkdtemp),
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch("app2nix.core.analyzers.appimage.shutil.rmtree") as mock_rmtree,
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            analyze_appimage(str(ai_path))

        mock_rmtree.assert_called_once()

    def test_cleanup_on_extraction_failure(self, tmp_path):
        """Temp directory should be cleaned up when both extraction methods fail."""
        ai_path = tmp_path / "broken-cleanup.AppImage"
        ai_path.write_bytes(b"x" * 100 + b"     12345")

        def track_mkdtemp(*args, **kwargs):
            d = tmp_path / "ai_fail_workdir"
            d.mkdir(exist_ok=True)
            return str(d)

        side_effect = make_appimage_side_effect(
            fuse_succeeds=False,
            unsquashfs_succeeds=False,
        )

        with (
            patch("app2nix.core.analyzers.appimage.tempfile.mkdtemp", side_effect=track_mkdtemp),
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch("app2nix.core.analyzers.appimage.shutil.rmtree") as mock_rmtree,
            patch.object(subprocess, "run", side_effect=side_effect),
            pytest.raises(ValueError, match="Failed to extract AppImage"),
        ):
            analyze_appimage(str(ai_path))

        mock_rmtree.assert_called_once()

    def test_cleanup_when_unsquashfs_missing(self, tmp_path):
        """Temp directory should be cleaned up when unsquashfs is not installed."""
        ai_path = tmp_path / "no-unsquashfs.AppImage"
        ai_path.write_text("fake")

        def track_mkdtemp(*args, **kwargs):
            d = tmp_path / "ai_no_unsq"
            d.mkdir(exist_ok=True)
            return str(d)

        with (
            patch("app2nix.core.analyzers.appimage.tempfile.mkdtemp", side_effect=track_mkdtemp),
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value=None),
            patch("app2nix.core.analyzers.appimage.shutil.rmtree") as mock_rmtree,
            pytest.raises(ValueError, match="unsquashfs"),
        ):
            analyze_appimage(str(ai_path))

        mock_rmtree.assert_called_once()

    def test_full_pipeline_analyze_to_nix_generation(self, tmp_path):
        """Full pipeline: AppImage analysis → resolve → generate."""
        ai_path = tmp_path / "pipeline-test.AppImage"
        ai_path.write_text("fake")
        ai_path.chmod(0o755)

        side_effect = make_appimage_side_effect(
            fuse_succeeds=True,
            patchelf_output="libssl.so.3\n",
        )

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            info = analyze_appimage(str(ai_path))

        resolver = DependencyResolver(tmp_path / "cache.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=resolved, unresolved=unresolved)

        assert result.package.name == "pipeline-test"
        assert result.package.format == "appimage"
        assert result.nix_content is not None
        assert "pipeline-test" in result.nix_content
        assert "mkDerivation" in result.nix_content
        assert result.flake_content is not None
        assert "pipeline-test" in result.flake_content
        # appimage phase should include --appimage-extract
        assert "appimage-extract" in result.nix_content or "appimage-extract" in result.install_script


# =============================================================================
# Snap
# =============================================================================


class TestSnapE2E:
    """E2E tests for Snap analysis (simple analyzer with minimal subprocess calls)."""

    def test_returns_basic_package_info(self, tmp_path):
        """analyze_snap returns PackageInfo with correct fields."""
        snap_path = tmp_path / "my-snap.snap"
        snap_path.write_text("fake snap")

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = ""
            info = analyze_snap(str(snap_path))

        assert info.name == "my-snap"
        assert info.version == "1.0"
        assert info.architecture == "x86_64"
        assert info.format == "snap"
        assert info.dependencies == []

    def test_handles_unsquashfs_not_found(self, tmp_path):
        """When unsquashfs is missing, the analyzer should not crash."""
        snap_path = tmp_path / "no-tools.snap"
        snap_path.write_text("fake")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("unsquashfs not found")):
            info = analyze_snap(str(snap_path))

        assert info.name == "no-tools"
        assert info.format == "snap"

    def test_snap_format_passes_through_pipeline(self, tmp_path):
        """Ensure snap info can flow through resolver and generator."""
        info = PackageInfo(
            name="my-snap",
            version="1.0",
            architecture="x86_64",
            format="snap",
            dependencies=[],
        )
        resolver = DependencyResolver(tmp_path / "cache.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=resolved, unresolved=unresolved)

        assert result.package.name == "my-snap"
        assert result.package.format == "snap"
        assert result.nix_content is not None
        assert "my-snap" in result.nix_content
        # snap uses the default install phase (not deb/appimage specific)
        assert result.validation_passed is True

    def test_cleanup_no_tempdir_needed(self, tmp_path):
        """Snap analyzer creates temp dirs for extraction, cleans up after."""
        snap_path = tmp_path / "no-cleanup.snap"
        snap_path.write_text("fake")

        with (
            patch("app2nix.core.analyzers.snap.subprocess.run") as mock_run,
            patch("app2nix.core.analyzers.snap.tempfile.mkdtemp") as mock_mkdtemp,
            patch("app2nix.core.analyzers.snap.shutil.rmtree"),
        ):
            mock_mkdtemp.return_value = str(tmp_path / "work")
            (tmp_path / "work").mkdir(exist_ok=True)
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            info = analyze_snap(str(snap_path))

        assert info.name == "no-cleanup"
        assert info.format == "snap"
        assert info.dependencies == []


# =============================================================================
# RPM
# =============================================================================


def make_rpm_side_effect(
    queryformat_output: str = "my-rpm\t2.0.1\tx86_64\n",
    requires_output: str = "libssl.so.3\nlibc.so.6\nrpmlib(CompressedFileSystem)\n",
    cpio_deps: list[str] | None = None,
) -> callable:
    """
    Build mock for ``subprocess`` calls made by ``analyze_rpm``.
    Handles ``check_output`` for rpm queries and ``Popen``/``run`` for cpio fallback.
    """
    def _check_output_side(cmd, **kwargs):
        if "--queryformat" in cmd:
            return queryformat_output
        if "--requires" in cmd:
            return requires_output
        raise subprocess.CalledProcessError(1, cmd)

    def _popen_side(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.wait.return_value = None
        return mock_proc

    def _run_side(cmd, **kwargs):
        if cmd[:2] == ["cpio", "-idmv"]:
            # Create some ELF files in the tmpdir for patchelf to find
            cwd = kwargs.get("cwd")
            if cwd:
                cwd = Path(cwd)
                (cwd / "usr").mkdir(parents=True, exist_ok=True)
                (cwd / "usr" / "bin" / "myapp").write_text("elf")
                (cwd / "usr" / "bin" / "myapp").chmod(0o755)
            return _make_elf_mock("")
        if cmd[:2] == ["patchelf", "--print-needed"]:
            libs = "\n".join(cpio_deps or ["libssl.so.3"]) + "\n"
            return _make_elf_mock(libs)
        return _make_elf_mock("")

    return {"check_output": _check_output_side, "run": _run_side, "Popen": _popen_side}


class TestRpmE2E:
    """E2E tests for RPM analysis with mocked subprocess."""

    def test_full_analysis_returns_complete_info(self, tmp_path):
        """Analyze an RPM and verify all fields from rpm query output."""
        rpm_path = tmp_path / "my-rpm-2.0.1-1.fc38.x86_64.rpm"
        rpm_path.write_text("fake rpm")

        side = make_rpm_side_effect()
        # Use a class to track calls
        check_output_side = side["check_output"]
        run_side = side["run"]

        with (
            patch.object(subprocess, "check_output", side_effect=check_output_side),
            patch.object(subprocess, "run", side_effect=run_side),
        ):
            info = analyze_rpm(str(rpm_path))

        assert info.name == "my-rpm"
        assert info.version == "2.0.1"
        assert info.architecture == "x86_64"
        assert info.format == "rpm"
        assert "ssl" in info.dependencies
        assert "c" in info.dependencies

    def test_fallback_to_cpio_when_rpm_missing(self, tmp_path):
        """When rpm commands fail, fall back to cpio-based extraction."""
        rpm_path = tmp_path / "no-rpm-1.0.x86_64.rpm"
        rpm_path.write_text("fake")

        with (
            patch.object(subprocess, "check_output", side_effect=FileNotFoundError("rpm not found")),
            patch.object(subprocess, "Popen") as mock_popen,
            patch.object(subprocess, "run") as mock_run,
        ):
            mock_proc = MagicMock()
            mock_proc.stdout = MagicMock()
            mock_proc.wait.return_value = None
            mock_popen.return_value = mock_proc

            def _run_side(cmd, **kwargs):
                if cmd[:2] == ["cpio", "-idmv"]:
                    cwd = Path(kwargs.get("cwd", "."))
                    if cwd:
                        (cwd / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                        (cwd / "usr" / "bin" / "app").write_text("elf")
                    return _make_elf_mock("")
                if cmd[:2] == ["patchelf", "--print-needed"]:
                    return _make_elf_mock("libssl.so.3\nlibz.so.1\n")
                return _make_elf_mock("")
            mock_run.side_effect = _run_side

            info = analyze_rpm(str(rpm_path))

        assert info.format == "rpm"
        assert "ssl" in info.dependencies
        assert "z" in info.dependencies

    def test_no_lib_deps_returns_empty(self, tmp_path):
        """RPM without lib*.so requires produce empty deps."""
        rpm_path = tmp_path / "no-deps-1.0.x86_64.rpm"
        rpm_path.write_text("fake")

        side = make_rpm_side_effect(
            requires_output="rpmlib(CompressedFileSystem)\n/sbin/ldconfig\n",
        )

        with (
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            info = analyze_rpm(str(rpm_path))

        assert info.dependencies == []

    def test_cleanup_when_no_cpio_needed(self, tmp_path):
        """No temp dir created when rpm commands succeed (no cpio fallback)."""
        rpm_path = tmp_path / "direct-1.0.x86_64.rpm"
        rpm_path.write_text("fake")

        tracked = []
        original_td = __import__("tempfile").TemporaryDirectory

        def tracking_td(*args, **kwargs):
            td = original_td(*args, **kwargs)
            tracked.append(td.name)
            return td

        side = make_rpm_side_effect()

        with (
            patch("app2nix.core.analyzers.rpm.tempfile.TemporaryDirectory", tracking_td),
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            info = analyze_rpm(str(rpm_path))

        # No temp dir created because rpm commands succeeded
        assert len(tracked) == 0
        assert info.format == "rpm"

    def test_cleanup_on_cpio_success(self, tmp_path):
        """Temp directory should be cleaned up after cpio-based extraction succeeds."""
        rpm_path = tmp_path / "cpio-ok-1.0.x86_64.rpm"
        rpm_path.write_text("fake")

        tracked = []
        original_td = __import__("tempfile").TemporaryDirectory

        def tracking_td(*args, **kwargs):
            td = original_td(*args, **kwargs)
            tracked.append(td.name)
            return td

        with (
            patch("app2nix.core.analyzers.rpm.tempfile.TemporaryDirectory", tracking_td),
            patch.object(subprocess, "check_output", side_effect=FileNotFoundError("rpm not found")),
            patch.object(subprocess, "Popen") as mock_popen,
            patch.object(subprocess, "run") as mock_run,
        ):
            mock_proc = MagicMock()
            mock_proc.stdout = MagicMock()
            mock_proc.wait.return_value = None
            mock_popen.return_value = mock_proc

            def _run_side(cmd, **kwargs):
                if cmd[:2] == ["cpio", "-idmv"]:
                    cwd = Path(kwargs.get("cwd", "."))
                    if cwd:
                        (cwd / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                        (cwd / "usr" / "bin" / "app").write_text("elf")
                    return _make_elf_mock("")
                if cmd[:2] == ["patchelf", "--print-needed"]:
                    return _make_elf_mock("libssl.so.3\n")
                return _make_elf_mock("")
            mock_run.side_effect = _run_side

            info = analyze_rpm(str(rpm_path))

        assert len(tracked) >= 1
        # TemporaryDirectory context manager should have cleaned up
        for d in tracked:
            assert not Path(d).exists(), f"Temp dir {d} was not cleaned up"
        assert info.format == "rpm"
        assert "ssl" in info.dependencies

    def test_cleanup_when_cpio_elf_scan_fails(self, tmp_path):
        """Temp directory should be cleaned up when patchelf scan fails during cpio extraction.

        Unlike deb/AppImage which use explicit ``shutil.rmtree``, the RPM analyzer
        uses ``tempfile.TemporaryDirectory`` (context manager) in
        ``_extract_deps_via_cpio``. Cleanup is verified by tracking the created
        directory and checking it no longer exists after the function returns.
        """
        rpm_path = tmp_path / "cpio-fail-1.0.x86_64.rpm"
        rpm_path.write_text("fake")

        tracked = []
        original_td = __import__("tempfile").TemporaryDirectory

        def tracking_td(*args, **kwargs):
            td = original_td(*args, **kwargs)
            tracked.append(td.name)
            return td

        patchelf_calls = 0

        def _run_side(cmd, **kwargs):
            nonlocal patchelf_calls
            if cmd[:2] == ["cpio", "-idmv"]:
                # Create ELF files so patchelf will be invoked
                cwd = Path(kwargs.get("cwd", "."))
                (cwd / "usr").mkdir(parents=True, exist_ok=True)
                (cwd / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (cwd / "usr" / "bin" / "myapp").write_text("elf")
                (cwd / "usr" / "bin" / "myapp").chmod(0o755)
                (cwd / "usr" / "lib").mkdir(parents=True, exist_ok=True)
                (cwd / "usr" / "lib" / "libhelper.so").write_text("elf")
                return _make_elf_mock("")
            if cmd[:2] == ["patchelf", "--print-needed"]:
                patchelf_calls += 1
                raise RuntimeError("patchelf failed")
            return _make_elf_mock("")

        with (
            patch("app2nix.core.analyzers.rpm.tempfile.TemporaryDirectory", tracking_td),
            patch.object(subprocess, "check_output", side_effect=FileNotFoundError("rpm not found")),
            patch.object(subprocess, "Popen") as mock_popen,
            patch.object(subprocess, "run", side_effect=_run_side),
        ):
            mock_proc = MagicMock()
            mock_proc.stdout = MagicMock()
            mock_proc.wait.return_value = None
            mock_popen.return_value = mock_proc

            info = analyze_rpm(str(rpm_path))

        assert patchelf_calls >= 1, f"patchelf was never called (called {patchelf_calls} times)"
        assert len(tracked) >= 1
        for d in tracked:
            assert not Path(d).exists(), f"Temp dir {d} was not cleaned up"
        assert info.format == "rpm"
        assert info.dependencies == []

    def test_full_pipeline_analyze_to_nix_generation(self, tmp_path):
        """Full pipeline: RPM analysis → resolve → generate."""
        rpm_path = tmp_path / "pipeline-rpm-3.0.x86_64.rpm"
        rpm_path.write_text("fake")

        side = make_rpm_side_effect(
            queryformat_output="pipeline-rpm\t3.0\tx86_64\n",
            requires_output="libssl.so.3\nlibz.so.1\n",
        )

        with (
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            info = analyze_rpm(str(rpm_path))

        resolver = DependencyResolver(tmp_path / "cache.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=resolved, unresolved=unresolved)

        assert result.package.name == "pipeline-rpm"
        assert result.package.format == "rpm"
        assert result.nix_content is not None
        assert "pipeline-rpm" in result.nix_content
        assert "mkDerivation" in result.nix_content
        # rpm format uses rpm2cpio install phase
        assert "rpm2cpio" in result.nix_content
        assert result.flake_content is not None
        assert "pipeline-rpm" in result.flake_content


# =============================================================================
# Flatpak
# =============================================================================


class TestFlatpakE2E:
    """E2E tests for Flatpak analysis with mocked subprocess."""

    def test_returns_basic_info_when_builder_missing(self, tmp_path):
        """When flatpak-builder is unavailable, return basic info from filename."""
        flatpak_path = tmp_path / "org.example.MyApp.flatpak"
        flatpak_path.write_text("fake")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("flatpak-builder not found")):
            info = analyze_flatpak(str(flatpak_path))

        assert info.name == "org.example.myapp"  # lowercased by sanitize_name
        assert info.version == "1.0"
        assert info.architecture == "x86_64"
        assert info.format == "flatpak"

    def test_parses_manifest_json(self, tmp_path):
        """When manifest exists in parent dir, parse JSON for app ID."""
        flatpak_path = tmp_path / "my-app.flatpak"
        flatpak_path.write_text("fake")
        # New implementation looks for manifest in parent dir
        manifest = tmp_path / "app.json"
        manifest.write_text('{"id": "org.foo.Bar", "version": "2.0"}')

        with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "unsquashfs")):
            info = analyze_flatpak(str(flatpak_path))

        assert info.name == "org.foo.bar"
        assert info.format == "flatpak"

    def test_cleanup_no_tempdir_needed(self, tmp_path):
        """Flatpak analyzer uses temp dirs for extraction, cleans up after."""
        flatpak_path = tmp_path / "org.example.NoCleanup.flatpak"
        flatpak_path.write_text("fake")
        # Put manifest in parent dir
        manifest = tmp_path / "app.json"
        manifest.write_text('{"id": "org.example.NoCleanup"}')

        with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "unsquashfs")):
            info = analyze_flatpak(str(flatpak_path))

        assert info.name == "org.example.nocleanup"
        assert info.format == "flatpak"
        assert info.dependencies == []

    def test_full_pipeline_flatpak_to_nix_generation(self, tmp_path):
        """Full pipeline: Flatpak analysis → resolve → generate."""
        info = PackageInfo(
            name="org.example.app",
            version="1.0",
            architecture="x86_64",
            format="flatpak",
            dependencies=["ssl"],
        )

        resolver = DependencyResolver(tmp_path / "cache.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=resolved, unresolved=unresolved)

        assert result.package.name == "org.example.app"
        assert result.package.format == "flatpak"
        assert result.nix_content is not None
        assert "org.example.app" in result.nix_content
        assert "mkDerivation" in result.nix_content
        # flatpak uses default install phase (not format-specific)
        assert result.validation_passed is True


# =============================================================================
# Tarball
# =============================================================================


def make_tarball_side_effect(
    tar_succeeds: bool = True,
    elf_files: tuple[str, ...] = ("myapp", "libhelper.so"),
    patchelf_output: str = "libssl.so.3\nlibc.so.6\n",
) -> callable:
    """
    Build a side_effect for ``subprocess.run`` that simulates the tools
    called by ``analyze_tarball``:

      1. ``[\"tar\", \"-xf\", <path>, \"-C\", <tmpdir>]``
      2. ``[\"file\", \"-b\", <f>]``                          (per file)
      3. ``[\"patchelf\", \"--print-needed\", <f>]``          (per ELF)
    """
    elf_side = _make_file_patchelf_side_effect(elf_files, patchelf_output)

    def _side_effect(cmd, **kwargs):
        # 1. tar -xf <src> -C <dest>
        if cmd[:2] == ["tar", "-xf"]:
            if tar_succeeds:
                c_idx = cmd.index("-C") + 1 if "-C" in cmd else None
                if c_idx is not None:
                    dest = Path(cmd[c_idx])
                    (dest / "usr").mkdir(parents=True, exist_ok=True)
                    (dest / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                    (dest / "usr" / "bin" / "myapp").write_text("elf")
                    (dest / "usr" / "bin" / "myapp").chmod(0o755)
                    (dest / "usr" / "lib").mkdir(parents=True, exist_ok=True)
                    (dest / "usr" / "lib" / "libhelper.so").write_text("elf")
            return _make_elf_mock("")

        # 2. file -b / patchelf --print-needed
        result = elf_side(cmd, **kwargs)
        if result is not None:
            return result

        return _make_elf_mock("")

    return _side_effect


class TestTarballE2E:
    """E2E tests for Tarball analysis with mocked subprocess."""

    def test_full_analysis_returns_complete_info(self, tmp_path):
        """Analyze a .tar.gz and verify all fields."""
        tar_path = tmp_path / "my-app-1.2.3.tar.gz"
        tar_path.write_text("fake tar")

        side_effect = make_tarball_side_effect(
            tar_succeeds=True,
            patchelf_output="libssl.so.3\nlibc.so.6\nlibz.so.1\n",
        )

        with (
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "tar_workdir")),
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "tar_workdir").mkdir(exist_ok=True)
            info = analyze_tarball(str(tar_path))

        assert info.name == "my-app-1.2.3"
        assert info.version == "1.0"
        assert info.architecture == "x86_64"
        assert info.format == "tarball"
        assert "ssl" in info.dependencies
        assert "c" in info.dependencies
        assert "z" in info.dependencies
        assert any("usr/bin/myapp" in e for e in info.executables)

    def test_tgz_format_parsed_correctly(self, tmp_path):
        """A .tgz file should be analysed with the correct name (stem stripped)."""
        tar_path = tmp_path / "archive.tgz"
        tar_path.write_text("fake")

        side_effect = make_tarball_side_effect(tar_succeeds=True)

        with (
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "tgz_workdir")),
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "tgz_workdir").mkdir(exist_ok=True)
            info = analyze_tarball(str(tar_path))

        assert info.name == "archive"
        assert info.format == "tarball"

    def test_no_elf_files_returns_empty_deps(self, tmp_path):
        """With no ELF files in the tarball, dependencies should be empty."""
        tar_path = tmp_path / "script-only.tar.gz"
        tar_path.write_text("fake")

        # Use a side_effect that never identifies anything as ELF
        def no_elf_side(cmd, **kwargs):
            if cmd[:2] == ["tar", "-xf"]:
                c_idx = cmd.index("-C") + 1
                dest = Path(cmd[c_idx])
                (dest / "usr").mkdir(parents=True, exist_ok=True)
                (dest / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (dest / "usr" / "bin" / "script").write_text("#!/bin/bash")
                return _make_elf_mock("")
            if cmd[:2] == ["file", "-b"]:
                return _make_elf_mock("Bourne-Again shell script, ASCII text executable")
            return _make_elf_mock("")

        with (
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "noelf_workdir")),
            patch.object(subprocess, "run", side_effect=no_elf_side),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "noelf_workdir").mkdir(exist_ok=True)
            info = analyze_tarball(str(tar_path))

        assert info.dependencies == []

    def test_cleanup_on_success(self, tmp_path):
        """Temp directory should be cleaned up after successful tarball analysis."""
        tar_path = tmp_path / "cleanup-ok-1.0.tar.gz"
        tar_path.write_text("fake")

        side_effect = make_tarball_side_effect(tar_succeeds=True)

        with (
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "tar_ok_workdir")),
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree") as mock_rmtree,
        ):
            (tmp_path / "tar_ok_workdir").mkdir(exist_ok=True)
            analyze_tarball(str(tar_path))

        mock_rmtree.assert_called_once()

    def test_cleanup_on_failure(self, tmp_path):
        """Temp directory should be cleaned up if extraction fails."""
        tar_path = tmp_path / "broken.tar"
        tar_path.write_text("fake")

        with (
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "fail_workdir")),
            patch.object(subprocess, "run", side_effect=Exception("tar extraction failed")),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree") as mock_rmtree,
        ):
            (tmp_path / "fail_workdir").mkdir(exist_ok=True)
            with pytest.raises(Exception, match="extraction"):
                analyze_tarball(str(tar_path))

        mock_rmtree.assert_called_once()

    def test_cleanup_on_patchelf_failure(self, tmp_path):
        """Temp directory should be cleaned up when patchelf raises exceptions."""
        tar_path = tmp_path / "patchelf-fail.tar.gz"
        tar_path.write_text("fake")

        def _run_side(cmd, **kwargs):
            if cmd[:2] == ["tar", "-xf"]:
                # Create files so patchelf is invoked
                c_idx = cmd.index("-C") + 1
                dest = Path(cmd[c_idx])
                (dest / "usr" / "bin").mkdir(parents=True, exist_ok=True)
                (dest / "usr" / "bin" / "myapp").write_text("elf")
                return _make_elf_mock("")
            if cmd[:2] == ["file", "-b"]:
                return _make_elf_mock("ELF 64-bit LSB executable, x86-64")
            if cmd[:2] == ["patchelf", "--print-needed"]:
                raise RuntimeError("patchelf failed")
            return _make_elf_mock("")

        with (
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "patchelf_fail_workdir")),
            patch.object(subprocess, "run", side_effect=_run_side),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree") as mock_rmtree,
        ):
            (tmp_path / "patchelf_fail_workdir").mkdir(exist_ok=True)
            info = analyze_tarball(str(tar_path))

        mock_rmtree.assert_called_once()
        # Even with patchelf failures, the function returns basic info
        assert info.format == "tarball"
        assert info.dependencies == []

    def test_full_pipeline_analyze_to_nix_generation(self, tmp_path):
        """Full pipeline: tarball analysis → resolve → generate."""
        tar_path = tmp_path / "tarpkg-1.0.tar.gz"
        tar_path.write_text("fake")

        side_effect = make_tarball_side_effect(
            tar_succeeds=True,
            patchelf_output="libssl.so.3\n",
        )

        with (
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "pipe_workdir")),
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "pipe_workdir").mkdir(exist_ok=True)
            info = analyze_tarball(str(tar_path))

        resolver = DependencyResolver(tmp_path / "cache.db")
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        generator = NixGenerator()
        result = generator.generate_default_nix(info, resolved_deps=resolved, unresolved=unresolved)

        assert result.package.name == "tarpkg-1.0"
        assert result.package.format == "tarball"
        assert result.nix_content is not None
        assert "tarpkg-1.0" in result.nix_content
        assert "mkDerivation" in result.nix_content
        assert result.flake_content is not None
        assert "tarpkg-1.0" in result.flake_content


# =============================================================================
# Server — cross-format endpoint tests
# =============================================================================


class TestServerCrossFormat:
    """Server-level E2E tests for multiple formats: mock only subprocess."""

    @pytest.mark.asyncio
    async def test_server_analyze_appimage(self, tmp_path):
        """POST /analyze should work with .AppImage when subprocess is mocked."""
        from app2nix.server import app

        ai_content = b"fake appimage"

        side_effect = make_appimage_side_effect(fuse_succeeds=True)

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("myapp.AppImage", ai_content, "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["format"] == "appimage"

    @pytest.mark.asyncio
    async def test_server_analyze_rpm(self, tmp_path):
        """POST /analyze should work with .rpm when subprocess is mocked."""
        from app2nix.server import app

        side = make_rpm_side_effect()

        with (
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("pkg.rpm", b"fake rpm", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["format"] == "rpm"
        assert data["name"] == "my-rpm"
        assert data["version"] == "2.0.1"

    @pytest.mark.asyncio
    async def test_server_generate_rpm(self, tmp_path):
        """POST /generate should work with .rpm when subprocess is mocked."""
        from app2nix.server import app

        side = make_rpm_side_effect(
            queryformat_output="rpm-server-gen\t2.5.0\tx86_64\n",
            requires_output="libssl.so.3\nlibz.so.1\n",
        )

        with (
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={"file": ("pkg.rpm", b"fake rpm", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "rpm-server-gen"
        assert data["version"] == "2.5.0"
        assert "mkDerivation" in data["content"]
        assert "rpm2cpio" in data["content"]
        assert data["validation_passed"] is True
        assert data["auto_install_script"] is not None
        assert data["install_guide"] is not None

    @pytest.mark.asyncio
    async def test_server_analyze_tarball(self, tmp_path):
        """POST /analyze should work with .tar.gz when subprocess is mocked."""
        from app2nix.server import app

        side_effect = make_tarball_side_effect(tar_succeeds=True)

        with (
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "srv_tar_analyze")),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "srv_tar_analyze").mkdir(exist_ok=True)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("my-app-1.0.tar.gz", b"fake tar", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["format"] == "tarball"
        assert data["name"] == "my-app-1.0"
        assert data["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_server_generate_tarball(self, tmp_path):
        """POST /generate should work with .tar.gz when subprocess is mocked."""
        from app2nix.server import app

        side_effect = make_tarball_side_effect(tar_succeeds=True)

        with (
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "srv_tar_workdir")),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "srv_tar_workdir").mkdir(exist_ok=True)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={"file": ("archive.tar.gz", b"fake tar", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] is not None
        assert "mkDerivation" in data["content"]
        assert data["validation_passed"] is True
        assert data["auto_install_script"] is not None
        assert data["install_guide"] is not None

    @pytest.mark.asyncio
    async def test_server_analyze_flatpak(self, tmp_path):
        """POST /analyze should work with .flatpak when flatpak-builder is mocked."""
        from app2nix.server import app

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("flatpak-builder not found")):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/analyze",
                    files={"file": ("org.example.ServerTest.flatpak", b"fake flatpak", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["format"] == "flatpak"
        assert data["name"] == "org.example.servertest"
        assert data["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_server_generate_flatpak(self, tmp_path):
        """POST /generate should work with .flatpak when flatpak-builder is mocked."""
        from app2nix.server import app

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("flatpak-builder not found")):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/generate",
                    files={"file": ("org.example.MyGen.flatpak", b"fake flatpak", "application/octet-stream")},
                )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "org.example.mygen"
        assert data["version"] == "1.0"
        assert "mkDerivation" in data["content"]
        assert "org.example.mygen" in data["content"]
        assert data["validation_passed"] is True
        assert data["auto_install_script"] is not None
        assert data["install_guide"] is not None


# =============================================================================
# CLI — cross-format tests
# =============================================================================


class TestCliCrossFormat:
    """CLI-level E2E tests for multiple formats using Typer CliRunner."""

    def test_cli_convert_rpm_with_mocked_subprocess(self, tmp_path):
        """Simulate 'app2nix convert package.rpm' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        rpm_file = tmp_path / "hello-rpm-1.0.x86_64.rpm"
        rpm_file.write_text("fake rpm")
        out_dir = tmp_path / "rpm-out"
        out_dir.mkdir()

        side = make_rpm_side_effect(
            queryformat_output="hello-rpm\t1.0\tx86_64\n",
            requires_output="libssl.so.3\n",
        )

        runner = CliRunner()
        with (
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            result = runner.invoke(
                app,
                ["convert", str(rpm_file), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Generated" in result.output
        nix_file = out_dir / "default.nix"
        assert nix_file.exists()
        content = nix_file.read_text()
        assert "hello-rpm" in content
        assert "mkDerivation" in content
        assert "rpm2cpio" in content

    def test_cli_convert_rpm_with_flake(self, tmp_path):
        """Simulate 'app2nix convert package.rpm --flake' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        rpm_file = tmp_path / "rpm-flake-3.0.x86_64.rpm"
        rpm_file.write_text("fake rpm")
        out_dir = tmp_path / "rpm-flake-out"
        out_dir.mkdir()

        side = make_rpm_side_effect(
            queryformat_output="rpm-flake\t3.0\tx86_64\n",
            requires_output="libssl.so.3\nlibz.so.1\n",
        )

        runner = CliRunner()
        with (
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            result = runner.invoke(
                app,
                ["convert", str(rpm_file), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "default.nix").exists()
        assert (out_dir / "flake.nix").exists()
        default_content = (out_dir / "default.nix").read_text()
        assert "rpm-flake" in default_content
        assert "rpm2cpio" in default_content
        flake_content = (out_dir / "flake.nix").read_text()
        assert "rpm-flake" in flake_content

    def test_cli_convert_rpm_print_deps(self, tmp_path):
        """Simulate 'app2nix convert package.rpm --print-deps' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        rpm_file = tmp_path / "deps-rpm-2.0.x86_64.rpm"
        rpm_file.write_text("fake rpm")

        side = make_rpm_side_effect(
            queryformat_output="deps-rpm\t2.0\tx86_64\n",
            requires_output="libssl.so.3\nlibc.so.6\n",
        )

        runner = CliRunner()
        with (
            patch.object(subprocess, "check_output", side_effect=side["check_output"]),
            patch.object(subprocess, "run", side_effect=side["run"]),
        ):
            result = runner.invoke(
                app,
                ["convert", str(rpm_file), "--print-deps"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Dependencies" in result.output
        assert "ssl" in result.output
        assert "c" in result.output

    def test_cli_convert_appimage_with_flake(self, tmp_path):
        """Simulate 'app2nix convert package.AppImage --flake' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        ai_file = tmp_path / "gui-app-2.0.AppImage"
        ai_file.write_text("fake")
        ai_file.chmod(0o755)
        out_dir = tmp_path / "ai-out"
        out_dir.mkdir()

        side_effect = make_appimage_side_effect(fuse_succeeds=True)

        runner = CliRunner()
        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            result = runner.invoke(
                app,
                ["convert", str(ai_file), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "default.nix").exists()
        assert (out_dir / "flake.nix").exists()
        flake_content = (out_dir / "flake.nix").read_text()
        assert "gui-app" in flake_content

    def test_cli_convert_appimage_print_deps(self, tmp_path):
        """Simulate 'app2nix convert package.AppImage --print-deps' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        ai_file = tmp_path / "deps-app-3.0.AppImage"
        ai_file.write_text("fake")
        ai_file.chmod(0o755)

        side_effect = make_appimage_side_effect(
            fuse_succeeds=True,
            patchelf_output="libssl.so.3\nlibc.so.6\n",
        )

        runner = CliRunner()
        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=side_effect),
        ):
            result = runner.invoke(
                app,
                ["convert", str(ai_file), "--print-deps"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Dependencies" in result.output
        assert "ssl" in result.output
        assert "c" in result.output

    def test_cli_convert_flatpak_with_json(self, tmp_path):
        """Simulate 'app2nix convert package.flatpak --json' with mocked subprocess."""
        import json

        from typer.testing import CliRunner

        from app2nix.cli import app

        flatpak_file = tmp_path / "org.example.FlatTest.flatpak"
        flatpak_file.write_text("fake")
        out_dir = tmp_path / "fp-out"
        out_dir.mkdir()

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=FileNotFoundError("flatpak-builder not found")),
        ):
            result = runner.invoke(
                app,
                ["convert", str(flatpak_file), "--output-dir", str(out_dir), "--json"],
            )

        assert result.exit_code == 0
        json_file = out_dir / "org.example.flattest.json"  # lowered by sanitize_name
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert data["name"] == "org.example.flattest"
        assert data["version"] == "1.0"

    def test_cli_convert_flatpak_with_flake(self, tmp_path):
        """Simulate 'app2nix convert package.flatpak --flake' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        flatpak_file = tmp_path / "org.example.FlakeTest.flatpak"
        flatpak_file.write_text("fake")
        out_dir = tmp_path / "fp-flake-out"
        out_dir.mkdir()

        def _run_side(cmd, **kwargs):
            """Handle flatpak-builder (analyzer) AND nix-instantiate (validator)."""
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = ""
            mock.stderr = ""
            return mock

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=_run_side):
            result = runner.invoke(
                app,
                ["convert", str(flatpak_file), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "default.nix").exists()
        assert (out_dir / "flake.nix").exists()
        default_content = (out_dir / "default.nix").read_text()
        assert "org.example.flaketest" in default_content
        assert "mkDerivation" in default_content
        flake_content = (out_dir / "flake.nix").read_text()
        assert "org.example.flaketest" in flake_content

    def test_cli_convert_tarball_with_flake(self, tmp_path):
        """Simulate 'app2nix convert package.tar.gz --flake' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        tar_file = tmp_path / "tar-flake-2.0.tar.gz"
        tar_file.write_text("fake tar")
        out_dir = tmp_path / "tar-flake-out"
        out_dir.mkdir()

        side_effect = make_tarball_side_effect(
            tar_succeeds=True,
            patchelf_output="libssl.so.3\nlibz.so.1\n",
        )

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "tar_flake_workdir")),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "tar_flake_workdir").mkdir(exist_ok=True)
            result = runner.invoke(
                app,
                ["convert", str(tar_file), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "default.nix").exists()
        assert (out_dir / "flake.nix").exists()
        default_content = (out_dir / "default.nix").read_text()
        assert "tar-flake-2.0" in default_content
        assert "mkDerivation" in default_content
        flake_content = (out_dir / "flake.nix").read_text()
        assert "tar-flake-2.0" in flake_content

    def test_cli_convert_tarball_print_deps(self, tmp_path):
        """Simulate 'app2nix convert package.tar.gz --print-deps' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        tar_file = tmp_path / "tar-deps-1.0.tar.gz"
        tar_file.write_text("fake tar")

        side_effect = make_tarball_side_effect(
            tar_succeeds=True,
            patchelf_output="libssl.so.3\nlibc.so.6\n",
        )

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=side_effect),
            patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp", return_value=str(tmp_path / "tar_deps_workdir")),
            patch("app2nix.core.analyzers.tarball.shutil.rmtree"),
        ):
            (tmp_path / "tar_deps_workdir").mkdir(exist_ok=True)
            result = runner.invoke(
                app,
                ["convert", str(tar_file), "--print-deps"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Dependencies" in result.output
        assert "ssl" in result.output
        assert "c" in result.output

    def test_cli_convert_snap_with_flake(self, tmp_path):
        """Simulate 'app2nix convert package.snap --flake' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        snap_file = tmp_path / "snap-flake-1.0.snap"
        snap_file.write_text("fake snap")
        out_dir = tmp_path / "snap-flake-out"
        out_dir.mkdir()

        def _run_side(cmd, **kwargs):
            """Handle unsquashfs -l (analyzer) AND nix-instantiate (validator)."""
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = ""
            mock.stderr = ""
            return mock

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=_run_side):
            result = runner.invoke(
                app,
                ["convert", str(snap_file), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed (exit {result.exit_code}): {result.output}"
        assert (out_dir / "default.nix").exists()
        assert (out_dir / "flake.nix").exists()
        default_content = (out_dir / "default.nix").read_text()
        assert "snap-flake" in default_content
        assert "mkDerivation" in default_content
        flake_content = (out_dir / "flake.nix").read_text()
        assert "snap-flake" in flake_content

    def test_cli_convert_snap_print_deps(self, tmp_path):
        """Simulate 'app2nix convert package.snap --print-deps' with mocked subprocess."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        snap_file = tmp_path / "snap-deps-2.0.snap"
        snap_file.write_text("fake snap")

        runner = CliRunner()
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = ""
            result = runner.invoke(
                app,
                ["convert", str(snap_file), "--print-deps"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Dependencies" in result.output

    def test_cli_convert_nonexistent_file_errors(self, tmp_path):
        """Non-existent file should exit with error regardless of format."""
        from typer.testing import CliRunner

        from app2nix.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["convert", str(tmp_path / "no-file.rpm")])
        assert result.exit_code != 0
        assert "File not found" in result.output



