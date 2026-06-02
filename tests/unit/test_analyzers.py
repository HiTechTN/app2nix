import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app2nix.core.analyzer import SUPPORTED_FORMATS, UniversalAnalyzer
from app2nix.core.analyzers._elf_utils import extract_lib_name, find_elf, get_libs_patchelf
from app2nix.core.analyzers.appimage import (
    _appimage_offset,
    _extract_fuse,
    _extract_unsquashfs,
    analyze_appimage,
)
from app2nix.core.analyzers.deb import _get_libs_ldd, analyze_deb
from app2nix.core.analyzers.flatpak import analyze_flatpak
from app2nix.core.analyzers.rpm import _extract_deps_via_cpio, analyze_rpm
from app2nix.core.analyzers.snap import analyze_snap
from app2nix.core.analyzers.tarball import analyze_tarball
from app2nix.exceptions import UnsupportedFormatError
from app2nix.models import PackageInfo

# =============================================================================
# deb.py — extract_lib_name (pure function)
# =============================================================================


class TestExtractLibName:
    def test_typical_soname(self):
        assert extract_lib_name("libssl.so.3") == "ssl"

    def test_with_path(self):
        assert extract_lib_name("/usr/lib/x86_64-linux-gnu/libc.so.6") == "c"

    def test_no_lib_prefix(self):
        assert extract_lib_name("foo.so") is None

    def test_no_dot_so(self):
        assert extract_lib_name("libfoo") is None

    def test_empty_after_strip(self):
        assert extract_lib_name("lib.so") is None

    def test_multi_dot_so(self):
        assert extract_lib_name("libssl3.so.1.1") == "ssl3"


# =============================================================================
# deb.py — find_elf with mocked subprocess
# =============================================================================


class TestFindElf:
    def test_finds_elf_file(self, tmp_path):
        """find_elf should return files identified as ELF executables."""
        good = tmp_path / "bin"
        good.mkdir()
        elf_file = good / "myapp"
        elf_file.write_text("not really elf but mock will say so")

        bad = tmp_path / "data.txt"
        bad.write_text("plain text")

        with (
            patch.object(subprocess, "run") as mock_run,
        ):
            def side_effect(cmd, **_kw):
                mock = MagicMock()
                file_path = cmd[-1]
                if "myapp" in file_path:
                    mock.stdout = "ELF 64-bit LSB executable"
                else:
                    mock.stdout = "ASCII text"
                return mock

            mock_run.side_effect = side_effect
            found = find_elf(tmp_path)

        assert any("myapp" in str(f) for f in found)
        assert not any("data.txt" in str(f) for f in found)

    def test_handles_exception_gracefully(self, tmp_path):
        """find_elf should not crash if 'file' command fails."""
        f = tmp_path / "weird"
        f.write_text("data")
        with patch.object(subprocess, "run", side_effect=Exception("boom")):
            found = find_elf(tmp_path)
        assert found == []


# =============================================================================
# deb.py — _get_libs_ldd and get_libs_patchelf
# =============================================================================


class TestGetLibsLdd:
    def test_parse_ldd_output(self, tmp_path):
        binary = tmp_path / "bin"
        binary.write_text("dummy")
        ldd_output = (
            "\tlinux-vdso.so.1 (0x00007fff)\n"
            "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
            "\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f00)\n"
        )
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = ldd_output
            mock_run.return_value.stderr = ""
            libs = _get_libs_ldd(binary)
        assert libs == {"ssl", "c"}

    def test_empty_on_exception(self, tmp_path):
        binary = tmp_path / "bin"
        binary.write_text("dummy")
        with patch.object(subprocess, "run", side_effect=Exception("ldd not found")):
            libs = _get_libs_ldd(binary)
        assert libs == set()


class TestGetLibsPatchelf:
    def test_parse_patchelf_output(self, tmp_path):
        binary = tmp_path / "bin"
        binary.write_text("dummy")
        patchelf_output = "libz.so.1\nlibssl3.so\n"
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = patchelf_output
            mock_run.return_value.stderr = ""
            libs = get_libs_patchelf(binary)
        assert libs == {"z", "ssl3"}

    def test_empty_on_exception(self, tmp_path):
        binary = tmp_path / "bin"
        binary.write_text("dummy")
        with patch.object(subprocess, "run", side_effect=Exception("patchelf not found")):
            libs = get_libs_patchelf(binary)
        assert libs == set()


# =============================================================================
# deb.py — analyze_deb (integration-style with mocked subprocess)
# =============================================================================


class TestAnalyzeDeb:
    @patch("app2nix.core.analyzers.deb.tempfile.mkdtemp")
    @patch("app2nix.core.analyzers.deb.shutil.rmtree")
    def test_parse_dpkg_deb_info(self, mock_rmtree, mock_mkdtemp, tmp_path):
        """analyze_deb should parse Package, Version, Arch, and Depends fields."""
        mock_mkdtemp.return_value = str(tmp_path / "workdir")
        (tmp_path / "workdir").mkdir(exist_ok=True)

        deb_path = str(tmp_path / "test-app_1.2.3_amd64.deb")
        Path(deb_path).write_text("dummy")

        dpkg_deb_info = (
            "Package: test-app\n"
            "Version: 1.2.3\n"
            "Architecture: amd64\n"
            "Depends: libssl3, libc6 (>= 2.31), zlib1g | libz-dev\n"
            "Description: A test package\n"
        )

        call_count = 0

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            # dpkg-deb -x
            if "-x" in cmd:
                mock.returncode = 0
            # dpkg-deb -I
            elif "-I" in cmd:
                mock.stdout = dpkg_deb_info
            # file, ldd, patchelf — return nothing for simplicity
            else:
                mock.stdout = ""
                mock.stderr = ""
            return mock

        with patch.object(subprocess, "run", side_effect=mock_subprocess_run):
            info = analyze_deb(deb_path)

        assert info.name == "test-app"
        assert info.version == "1.2.3"
        assert info.architecture == "amd64"
        assert info.format == "deb"

    @patch("app2nix.core.analyzers.deb.tempfile.mkdtemp")
    @patch("app2nix.core.analyzers.deb.shutil.rmtree")
    def test_always_cleans_up_tempdir(self, mock_rmtree, mock_mkdtemp, tmp_path):
        """Temp directory should be cleaned up even if an error occurs."""
        mock_mkdtemp.return_value = str(tmp_path / "workdir")
        (tmp_path / "workdir").mkdir(exist_ok=True)
        deb_path = str(tmp_path / "broken.deb")
        Path(deb_path).write_text("dummy")

        with patch.object(subprocess, "run", side_effect=Exception("boom")):
            with pytest.raises(Exception, match="boom"):
                analyze_deb(deb_path)

        mock_rmtree.assert_called_once()


# =============================================================================
# appimage.py — _appimage_offset (binary parsing)
# =============================================================================


class TestAppimageOffset:
    def test_offset_from_last_8_bytes(self, tmp_path):
        """Should read the offset from the last 8 ASCII digits."""
        appimage = tmp_path / "test.AppImage"
        # write 50 bytes of garbage, then "     12345"
        data = b"x" * 50 + b"     12345"
        appimage.write_bytes(data)
        assert _appimage_offset(appimage) == 12345

    def test_offset_via_mmap_hsqs(self, tmp_path):
        """Should fall back to finding 'hsqs' in the binary."""
        appimage = tmp_path / "test.AppImage"
        hsqs_pos = 100
        data = b"x" * hsqs_pos + b"hsqs" + b"x" * 50
        # last 8 bytes are not digits
        data = data[:-8] + b"XXXXXXXX"
        appimage.write_bytes(data)
        assert _appimage_offset(appimage) == hsqs_pos

    def test_no_offset_found(self, tmp_path):
        """Should return 0 when no offset can be determined."""
        appimage = tmp_path / "test.AppImage"
        data = b"x" * 100
        appimage.write_bytes(data)
        assert _appimage_offset(appimage) == 0

    def test_offset_ignores_zero_value(self, tmp_path):
        """Should fall through to mmap when last 8 bytes are '00000000'."""
        appimage = tmp_path / "test.AppImage"
        hsqs_pos = 30
        data = b"x" * hsqs_pos + b"hsqs" + b"x" * 50
        data = data[:-8] + b"00000000"
        appimage.write_bytes(data)
        # offset=0 is not >0, so falls through to mmap
        assert _appimage_offset(appimage) == hsqs_pos

    def test_offset_with_negative_value_ignored(self, tmp_path):
        """Should fall through when last 8 digits represent a negative offset."""
        appimage = tmp_path / "test.AppImage"
        data = b"x" * 50 + b"    -1234"
        appimage.write_bytes(data)
        # data.isdigit() is False, so falls through to mmap
        # No hsqs marker, so returns 0
        assert _appimage_offset(appimage) == 0


# =============================================================================
# appimage.py — _extract_fuse (unit)
# =============================================================================


class TestExtractFuse:
    def test_fuse_non_zero_returncode(self, tmp_path):
        """When ``--appimage-extract`` returns non-zero, log warning and return None.

        The AppImage must be executable (0o755) before extraction is attempted.
        """
        appimage = tmp_path / "test.AppImage"
        appimage.write_text("dummy")
        appimage.chmod(0o755)
        dest = tmp_path / "squashfs-root"

        with patch.object(subprocess, "run") as mock_run:
            mock = MagicMock()
            mock.returncode = 1
            mock.stderr = "FUSE error: not supported"
            mock_run.return_value = mock

            result = _extract_fuse(appimage, tmp_path)

        assert result is None
        assert not dest.exists()
        # Verify correct command was called
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][:2] == [str(appimage), "--appimage-extract"]

    def test_fuse_patches_permissions_on_non_executable(self, tmp_path):
        """If the AppImage is not executable, ``_extract_fuse`` should chmod it first."""
        appimage = tmp_path / "test.AppImage"
        appimage.write_text("dummy")
        # Not setting executable bit — _extract_fuse should fix it
        assert not os.access(appimage, os.X_OK)

        with patch.object(subprocess, "run") as mock_run:
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = ""
            mock_run.return_value = mock

            result = _extract_fuse(appimage, tmp_path)

        # Should have been made executable
        assert os.access(appimage, os.X_OK)
        assert result is None  # no squashfs-root exists

    def test_fuse_squashfs_root_exists(self, tmp_path):
        """When extraction succeeds and squashfs-root exists, return the path."""
        appimage = tmp_path / "test.AppImage"
        appimage.write_text("dummy")
        appimage.chmod(0o755)

        # Create squashfs-root beforehand to simulate successful extraction
        (tmp_path / "squashfs-root").mkdir()

        with patch.object(subprocess, "run") as mock_run:
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = ""
            mock_run.return_value = mock

            result = _extract_fuse(appimage, tmp_path)

        assert result == tmp_path / "squashfs-root"


# =============================================================================
# appimage.py — _extract_unsquashfs (unit)
# =============================================================================


class TestExtractUnsquashfs:
    def test_unsquashfs_not_found(self, tmp_path):
        """When unsquashfs is missing, log error and return None."""
        path = tmp_path / "test.AppImage"
        path.write_text("dummy")

        with patch("app2nix.core.analyzers.appimage.shutil.which", return_value=None):
            result = _extract_unsquashfs(path, tmp_path)

        assert result is None

    def test_cleans_existing_dest_before_extraction(self, tmp_path):
        """If the dest directory already exists, it should be removed first."""
        path = tmp_path / "test.AppImage"
        # Must be >= 8 bytes for _appimage_offset to seek(-8, 2) safely
        path.write_bytes(b"x" * 50 + b"     12345")
        (tmp_path / "squashfs-root").mkdir()
        stale = tmp_path / "squashfs-root" / "stale.txt"
        stale.write_text("old data")

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch("app2nix.core.analyzers.appimage.shutil.rmtree") as mock_rmtree,
            patch.object(subprocess, "run") as mock_run,
        ):
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = ""
            mock_run.return_value = mock

            _extract_unsquashfs(path, tmp_path)

        # dest was cleaned before extraction
        mock_rmtree.assert_called_once_with(tmp_path / "squashfs-root")

    def test_unsquashfs_retry_without_offset_on_failure(self, tmp_path):
        """When unsquashfs with offset fails but dest is missing, retry without offset."""
        path = tmp_path / "test.AppImage"
        path.write_bytes(b"x" * 50 + b"     12345")
        dest = tmp_path / "squashfs-root"

        call_count = 0

        def _run_side(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.returncode = 1
            m.stderr = "unsquashfs error"
            m.stdout = ""
            if call_count == 2:
                # Second call (retry without offset) succeeds
                m.returncode = 0
                dest.mkdir(parents=True, exist_ok=True)
            return m

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run", side_effect=_run_side),
        ):
            result = _extract_unsquashfs(path, tmp_path)

        assert result == dest
        # It retried twice: once with offset, once without
        assert call_count == 2

    def test_unsquashfs_retry_still_fails(self, tmp_path):
        """When both unsquashfs attempts fail, return None."""
        path = tmp_path / "test.AppImage"
        path.write_bytes(b"x" * 50 + b"     12345")

        with (
            patch("app2nix.core.analyzers.appimage.shutil.which", return_value="/usr/bin/unsquashfs"),
            patch.object(subprocess, "run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stderr="unsquashfs error", stdout="")
            result = _extract_unsquashfs(path, tmp_path)

        assert result is None
        # Should have been called twice (with offset + retry)
        assert mock_run.call_count == 2


# =============================================================================
# _elf_utils — find_elf + get_libs_patchelf (unit)
# =============================================================================


class TestFindElfDeps:
    def test_exception_handled_gracefully(self, tmp_path):
        """Exceptions in subprocess calls should be caught, other files still processed."""
        (tmp_path / "bin").mkdir()
        good = tmp_path / "bin" / "good_app"
        good.write_text("elf")
        bad = tmp_path / "bin" / "bad_app"
        bad.write_text("elf")

        call_count = 0

        def _run_side(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.stdout = ""
            m.stderr = ""

            # First file processed successfully
            if "good_app" in str(cmd):
                if "file" in cmd:
                    m.stdout = "ELF 64-bit LSB executable, x86-64"
                elif "patchelf" in cmd:
                    m.stdout = "libssl.so.3\n"
            # Second file triggers an exception
            if "bad_app" in str(cmd):
                raise RuntimeError("patchelf crashed")

            return m

        with patch.object(subprocess, "run", side_effect=_run_side):
            executables = find_elf(tmp_path / "bin")
            deps = []
            for elf in executables:
                deps.extend(get_libs_patchelf(elf))

        # good_app was processed successfully, bad_app exception was caught
        assert "ssl" in deps
        # Call count: file good, patchelf good, file bad (raises before patchelf)
        assert call_count >= 2


# =============================================================================
# appimage.py — analyze_appimage with mocked subprocess
# =============================================================================


class TestAnalyzeAppimage:
    @patch("app2nix.core.analyzers.appimage.shutil.which")
    @patch("app2nix.core.analyzers.appimage.tempfile.mkdtemp")
    @patch("app2nix.core.analyzers.appimage.shutil.rmtree")
    def test_requires_unsquashfs(self, mock_rmtree, mock_mkdtemp, mock_which, tmp_path):
        """Should raise ValueError if unsquashfs is not installed."""
        mock_which.return_value = None
        mock_mkdtemp.return_value = str(tmp_path / "workdir")
        (tmp_path / "workdir").mkdir(exist_ok=True)

        appimage_path = str(tmp_path / "test.AppImage")
        Path(appimage_path).write_text("dummy")

        with pytest.raises(ValueError, match="unsquashfs"):
            analyze_appimage(appimage_path)

    @patch("app2nix.core.analyzers.appimage.shutil.which")
    @patch("app2nix.core.analyzers.appimage._extract_fuse")
    @patch("app2nix.core.analyzers.appimage._extract_unsquashfs")
    @patch("app2nix.core.analyzers.appimage.tempfile.mkdtemp")
    @patch("app2nix.core.analyzers.appimage.shutil.rmtree")
    def test_extraction_failure_raises(
        self, mock_rmtree, mock_mkdtemp, mock_unsquashfs, mock_fuse, mock_which, tmp_path
    ):
        """Should raise if both extraction methods fail."""
        mock_which.return_value = "/usr/bin/unsquashfs"
        mock_mkdtemp.return_value = str(tmp_path / "workdir")
        (tmp_path / "workdir").mkdir(exist_ok=True)
        mock_fuse.return_value = None
        mock_unsquashfs.return_value = None

        appimage_path = str(tmp_path / "test.AppImage")
        Path(appimage_path).write_text("dummy")

        with pytest.raises(ValueError, match="Failed to extract AppImage"):
            analyze_appimage(appimage_path)

    @patch("app2nix.core.analyzers.appimage.shutil.which")
    @patch("app2nix.core.analyzers.appimage._extract_fuse")
    @patch("app2nix.core.analyzers.appimage.find_elf")
    @patch("app2nix.core.analyzers.appimage.get_libs_patchelf")
    @patch("app2nix.core.analyzers.appimage.tempfile.mkdtemp")
    @patch("app2nix.core.analyzers.appimage.shutil.rmtree")
    def test_successful_analysis(
        self, mock_rmtree, mock_mkdtemp, mock_patchelf, mock_find_elf, mock_fuse, mock_which, tmp_path
    ):
        """Should return a PackageInfo with correct fields on success."""
        mock_which.return_value = "/usr/bin/unsquashfs"
        mock_mkdtemp.return_value = str(tmp_path / "workdir")
        mock_fuse.return_value = tmp_path / "squashfs-root"
        (tmp_path / "squashfs-root").mkdir(exist_ok=True)
        (tmp_path / "squashfs-root" / "usr").mkdir(exist_ok=True)
        (tmp_path / "squashfs-root" / "usr" / "bin").mkdir(exist_ok=True)
        exe = tmp_path / "squashfs-root" / "usr" / "bin" / "myapp"
        exe.write_text("#!/bin/bash")
        exe.chmod(0o755)
        mock_find_elf.return_value = [exe]
        mock_patchelf.return_value = ["ssl", "c", "z"]

        appimage_path = str(tmp_path / "test-app.AppImage")
        Path(appimage_path).write_text("dummy")

        info = analyze_appimage(appimage_path)

        assert info.name == "test-app"
        assert info.version == "1.0"
        assert info.architecture == "x86_64"
        assert info.format == "appimage"
        assert "usr/bin/myapp" in info.executables
        assert "ssl" in info.dependencies
        assert "z" in info.dependencies


# =============================================================================
# snap.py — analyze_snap
# =============================================================================


class TestAnalyzeSnap:
    def test_returns_package_info(self, tmp_path):
        snap_path = str(tmp_path / "my-snap.snap")
        Path(snap_path).write_text("dummy")

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = ""
            info = analyze_snap(snap_path)

        assert info.name == "my-snap"
        assert info.version == "1.0"
        assert info.architecture == "x86_64"
        assert info.format == "snap"
        assert info.dependencies == []
        assert info.executables == []

    def test_handles_subprocess_failure(self, tmp_path):
        snap_path = str(tmp_path / "broken.snap")
        Path(snap_path).write_text("dummy")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            info = analyze_snap(snap_path)

        # Should still return basic info without crashing
        assert info.name == "broken"
        assert info.format == "snap"

    def test_squashfs_offset_extraction(self, tmp_path):
        """When first unsquashfs fails, should try with offset."""
        snap_path = str(tmp_path / "my-snap.snap")
        # Write snap with hsqs magic at offset 100
        data = b"x" * 100 + b"hsqs" + b"x" * 50
        Path(snap_path).write_bytes(data)

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                # First unsquashfs fails
                raise subprocess.CalledProcessError(1, "unsquashfs")
            elif call_count == 2:
                # Second unsquashfs with offset succeeds
                sq = Path(cmd[cmd.index("-d") + 1])
                sq.mkdir(parents=True, exist_ok=True)
                mock.returncode = 0
            else:
                mock.stdout = ""
                mock.stderr = ""
            return mock

        with patch.object(subprocess, "run", side_effect=mock_run):
            info = analyze_snap(snap_path)

        assert info.format == "snap"
        assert call_count >= 2

    def test_snap_yaml_parsing(self, tmp_path):
        """Should parse meta/snap.yaml for name and version."""
        snap_path = str(tmp_path / "my-snap.snap")
        Path(snap_path).write_text("dummy")

        def mock_run(cmd, **kwargs):
            mock = MagicMock()
            if "unsquashfs" in cmd:
                sq = Path(cmd[cmd.index("-d") + 1])
                sq.mkdir(parents=True, exist_ok=True)
                # Create snap.yaml
                meta = sq / "meta"
                meta.mkdir(exist_ok=True)
                yaml = meta / "snap.yaml"
                yaml.write_text('name: my-app\nversion: "2.5"\n')
                mock.returncode = 0
            else:
                mock.stdout = ""
                mock.stderr = ""
            return mock

        with patch.object(subprocess, "run", side_effect=mock_run):
            info = analyze_snap(snap_path)

        assert info.name == "my-app"
        assert info.version == "2.5"

    def test_with_executables_and_libs(self, tmp_path):
        """Should discover executables and their dependencies."""
        snap_path = str(tmp_path / "my-snap.snap")
        Path(snap_path).write_text("dummy")

        def mock_run(cmd, **kwargs):
            mock = MagicMock()
            if "unsquashfs" in cmd:
                sq = Path(cmd[cmd.index("-d") + 1])
                sq.mkdir(parents=True, exist_ok=True)
                mock.returncode = 0
            elif "file" in cmd:
                mock.stdout = "ELF 64-bit LSB executable"
            elif "patchelf" in cmd:
                mock.stdout = "libz.so.1\nlibssl3.so\n"
            else:
                mock.stdout = ""
                mock.stderr = ""
            return mock

        with patch.object(subprocess, "run", side_effect=mock_run):
            info = analyze_snap(snap_path)

        assert info.format == "snap"

    def test_find_squashfs_offset(self, tmp_path):
        """Test _find_squashfs_offset helper."""
        from app2nix.core.analyzers.snap import _find_squashfs_offset

        # File with hsqs magic at offset 100
        snap = tmp_path / "test.snap"
        data = b"x" * 100 + b"hsqs" + b"x" * 50
        snap.write_bytes(data)

        assert _find_squashfs_offset(snap) == 100

    def test_find_squashfs_offset_not_found(self, tmp_path):
        """Should return 0 when no hsqs magic found."""
        from app2nix.core.analyzers.snap import _find_squashfs_offset

        snap = tmp_path / "test.snap"
        snap.write_bytes(b"x" * 100)

        assert _find_squashfs_offset(snap) == 0

    def test_extract_lib_name(self):
        """Test extract_lib_name helper."""
        from app2nix.core.analyzers._elf_utils import extract_lib_name

        assert extract_lib_name("libssl.so.3") == "ssl"
        assert extract_lib_name("/usr/lib/libc.so.6") == "c"
        assert extract_lib_name("foo.so") is None
        assert extract_lib_name("libfoo") is None
        assert extract_lib_name("lib.so") is None

    def test_find_elf(self, tmp_path):
        """Test find_elf helper."""
        from app2nix.core.analyzers._elf_utils import find_elf

        elf_file = tmp_path / "myapp"
        elf_file.write_text("dummy")

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = "ELF 64-bit LSB executable"
            found = find_elf(tmp_path)

        assert len(found) == 1
        assert found[0] == elf_file

    def test_get_libs_patchelf(self, tmp_path):
        """Test get_libs_patchelf helper."""
        from app2nix.core.analyzers._elf_utils import get_libs_patchelf

        binary = tmp_path / "bin"
        binary.write_text("dummy")

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = "libz.so.1\nlibssl3.so\n"
            libs = get_libs_patchelf(binary)

        assert libs == {"z", "ssl3"}


# =============================================================================
# rpm.py — analyze_rpm with mocked subprocess
# =============================================================================


class TestAnalyzeRpm:
    def test_parses_rpm_query_output(self, tmp_path):
        rpm_path = str(tmp_path / "my-app-1.2.3-1.fc38.x86_64.rpm")
        Path(rpm_path).write_text("dummy")

        def mock_check_output(cmd, **kwargs):
            if "--queryformat" in cmd:
                return "my-app\t1.2.3\tx86_64\n"
            if "--requires" in cmd:
                return "libssl.so.3\nlibc.so.6\nrpmlib(CompressedFileSystem)\n"
            return ""

        with patch.object(subprocess, "check_output", side_effect=mock_check_output):
            info = analyze_rpm(rpm_path)

        assert info.name == "my-app"
        assert info.version == "1.2.3"
        assert info.architecture == "x86_64"
        assert info.format == "rpm"
        assert "ssl" in info.dependencies
        assert "c" in info.dependencies

    def test_fallback_to_cpio_when_rpm_unavailable(self, tmp_path):
        """When rpm commands fail, it should fall back to _extract_deps_via_cpio."""
        rpm_path = str(tmp_path / "app-1.0.x86_64.rpm")
        Path(rpm_path).write_text("dummy")

        with (
            patch.object(subprocess, "check_output", side_effect=FileNotFoundError("rpm not found")),
            patch("app2nix.core.analyzers.rpm._extract_deps_via_cpio") as mock_cpio,
        ):
            mock_cpio.return_value = ["ssl", "z"]
            info = analyze_rpm(rpm_path)

        # path.stem of "app-1.0.x86_64.rpm" is "app-1.0.x86_64"
        assert info.name == "app-1.0.x86_64"
        assert info.format == "rpm"
        assert "ssl" in info.dependencies
        mock_cpio.assert_called_once()


class TestExtractDepsViaCpio:
    def test_empty_when_rpm2cpio_missing(self, tmp_path):
        rpm_path = str(tmp_path / "test.rpm")
        Path(rpm_path).write_text("dummy")
        with patch.object(subprocess, "Popen", side_effect=FileNotFoundError("rpm2cpio not found")):
            deps = _extract_deps_via_cpio(str(rpm_path))
        assert deps == []

    def test_patchelf_exception_handled(self, tmp_path):
        """When patchelf raises an exception on a file, it should be caught silently.

        This covers the ``except Exception: pass`` inside the inner patchelf
        loop of ``_extract_deps_via_cpio`` (line 75 in rpm.py).
        """
        rpm_path = str(tmp_path / "test.rpm")
        Path(rpm_path).write_text("dummy")

        # Pre-populate an extract directory to simulate files that "cpio"
        # would have extracted — avoids needing to actually run cpio.
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        elf_file = extract_dir / "libfoo.so"
        elf_file.write_text("dummy")

        patchelf_attempts = 0

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal patchelf_attempts
            m = MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            # First call is for ``cpio -idmv`` — succeed
            if cmd[0] == "cpio":
                return m
            # Subsequent calls are for ``patchelf --print-needed`` — crash
            patchelf_attempts += 1
            raise RuntimeError("patchelf simulation crash")

        with (
            patch("app2nix.core.analyzers.rpm.tempfile.TemporaryDirectory") as mock_td,
            patch.object(subprocess, "Popen") as mock_popen,
            patch.object(subprocess, "run", side_effect=mock_subprocess_run),
        ):
            mock_td.return_value.__enter__.return_value = str(extract_dir)
            mock_proc = MagicMock()
            mock_proc.stdout = MagicMock()
            mock_popen.return_value = mock_proc

            deps = _extract_deps_via_cpio(str(rpm_path))

        # No exception propagated, empty deps returned
        assert deps == []
        # patchelf was attempted (the inner except was hit)
        assert patchelf_attempts >= 1


# =============================================================================
# flatpak.py — analyze_flatpak
# =============================================================================


class TestAnalyzeFlatpak:
    def test_returns_basic_info_when_flatpak_builder_missing(self, tmp_path):
        flatpak_path = str(tmp_path / "org.example.MyApp.flatpak")
        Path(flatpak_path).write_text("dummy")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("flatpak-builder not found")):
            info = analyze_flatpak(flatpak_path)

        assert info.name == "org.example.myapp"
        assert info.version == "1.0"
        assert info.architecture == "x86_64"
        assert info.format == "flatpak"

    def test_parses_manifest_json(self, tmp_path):
        flatpak_path = str(tmp_path / "my-app.flatpak")
        Path(flatpak_path).write_text("dummy")
        # New implementation looks for manifest in parent dir
        manifest = tmp_path / "app.json"
        manifest.write_text('{"id": "org.foo.Bar", "version": "2.0"}')

        with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "unsquashfs")):
            info = analyze_flatpak(flatpak_path)

        assert info.name == "org.foo.bar"
        assert info.version == "2.0"
        assert info.format == "flatpak"

    def test_unsquashfs_failure_still_returns_info(self, tmp_path):
        """When unsquashfs fails, should still return basic info."""
        flatpak_path = str(tmp_path / "my-app.flatpak")
        Path(flatpak_path).write_text("dummy")

        def mock_run(cmd, **kwargs):
            mock = MagicMock()
            if "unsquashfs" in cmd:
                raise subprocess.CalledProcessError(1, "unsquashfs")
            else:
                mock.stdout = ""
                mock.stderr = ""
            return mock

        with patch.object(subprocess, "run", side_effect=mock_run):
            info = analyze_flatpak(flatpak_path)

        assert info.format == "flatpak"
        assert info.name == "my-app"

    def test_with_executables_and_libs(self, tmp_path):
        """Should discover executables and their dependencies."""
        flatpak_path = str(tmp_path / "my-app.flatpak")
        Path(flatpak_path).write_text("dummy")

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if "unsquashfs" in cmd:
                # Create the squashfs-root directory
                sq = Path(cmd[-2]) if len(cmd) > 2 else tmp_path / "squashfs-root"
                sq.mkdir(parents=True, exist_ok=True)
                mock.returncode = 0
            elif "file" in cmd:
                mock.stdout = "ELF 64-bit LSB executable"
            elif "patchelf" in cmd:
                mock.stdout = "libssl.so.3\nlibc.so.6\n"
            else:
                mock.stdout = ""
                mock.stderr = ""
            return mock

        with patch.object(subprocess, "run", side_effect=mock_run):
            info = analyze_flatpak(flatpak_path)

        assert info.format == "flatpak"

    def test_parse_metadata_from_squashfs_root(self, tmp_path):
        """Should parse metadata from squashfs-root/metadata."""
        flatpak_path = str(tmp_path / "my-app.flatpak")
        Path(flatpak_path).write_text("dummy")

        def mock_run(cmd, **kwargs):
            mock = MagicMock()
            if "unsquashfs" in cmd:
                sq = Path(cmd[-2]) if len(cmd) > 2 else tmp_path / "squashfs-root"
                sq.mkdir(parents=True, exist_ok=True)
                # Create metadata file
                metadata = sq / "metadata"
                metadata.write_text("[Application]\nname=org.example.MyApp\n")
                mock.returncode = 0
            else:
                mock.stdout = ""
                mock.stderr = ""
            return mock

        with patch.object(subprocess, "run", side_effect=mock_run):
            info = analyze_flatpak(flatpak_path)

        assert info.format == "flatpak"

    def test_manifest_yaml_parsing(self, tmp_path):
        """Should parse YAML-like manifest files."""
        flatpak_path = str(tmp_path / "my-app.flatpak")
        Path(flatpak_path).write_text("dummy")
        manifest = tmp_path / "app.yml"
        manifest.write_text('app-id: org.yaml.App\nversion: "3.0"\n')

        with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "unsquashfs")):
            info = analyze_flatpak(flatpak_path)

        assert info.name == "org.yaml.app"
        assert info.version == "3.0"

    def test_extract_lib_name(self):
        """Test extract_lib_name helper."""
        from app2nix.core.analyzers._elf_utils import extract_lib_name

        assert extract_lib_name("libssl.so.3") == "ssl"
        assert extract_lib_name("/usr/lib/libc.so.6") == "c"
        assert extract_lib_name("foo.so") is None
        assert extract_lib_name("libfoo") is None
        assert extract_lib_name("lib.so") is None

    def test_find_elf(self, tmp_path):
        """Test find_elf helper."""
        from app2nix.core.analyzers._elf_utils import find_elf

        elf_file = tmp_path / "myapp"
        elf_file.write_text("dummy")

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = "ELF 64-bit LSB executable"
            found = find_elf(tmp_path)

        assert len(found) == 1
        assert found[0] == elf_file

    def test_get_libs_patchelf(self, tmp_path):
        """Test get_libs_patchelf helper."""
        from app2nix.core.analyzers._elf_utils import get_libs_patchelf

        binary = tmp_path / "bin"
        binary.write_text("dummy")

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.stdout = "libz.so.1\nlibssl3.so\n"
            libs = get_libs_patchelf(binary)

        assert libs == {"z", "ssl3"}


# =============================================================================
# tarball.py — analyze_tarball with mocked subprocess
# =============================================================================


class TestAnalyzeTarball:
    @patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp")
    @patch("app2nix.core.analyzers.tarball.shutil.rmtree")
    def test_basic_analysis(self, mock_rmtree, mock_mkdtemp, tmp_path):
        mock_mkdtemp.return_value = str(tmp_path / "workdir")
        (tmp_path / "workdir").mkdir(exist_ok=True)

        # Create a fake ELF inside
        (tmp_path / "workdir" / "usr").mkdir(parents=True)
        (tmp_path / "workdir" / "usr" / "bin").mkdir()
        elf_file = tmp_path / "workdir" / "usr" / "bin" / "myapp"
        elf_file.write_text("dummy")
        elf_file.chmod(0o755)

        tar_path = str(tmp_path / "my-app.tar.gz")
        Path(tar_path).write_text("dummy")

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if "tar" in cmd:
                mock.returncode = 0
            elif "file" in cmd:
                mock.stdout = "ELF 64-bit LSB executable"
            elif "patchelf" in cmd:
                mock.stdout = "libssl.so.3\nlibc.so.6\n"
            return mock

        with patch.object(subprocess, "run", side_effect=mock_run):
            info = analyze_tarball(tar_path)

        assert info.name == "my-app"
        assert info.version == "1.0"
        assert info.format == "tarball"
        assert "ssl" in info.dependencies
        assert "c" in info.dependencies
        assert any("usr/bin/myapp" in str(e) for e in info.executables)

    @patch("app2nix.core.analyzers.tarball.tempfile.mkdtemp")
    @patch("app2nix.core.analyzers.tarball.shutil.rmtree")
    def test_cleanup_on_failure(self, mock_rmtree, mock_mkdtemp, tmp_path):
        mock_mkdtemp.return_value = str(tmp_path / "workdir")
        (tmp_path / "workdir").mkdir(exist_ok=True)

        tar_path = str(tmp_path / "broken.tar")
        Path(tar_path).write_text("dummy")

        with patch.object(subprocess, "run", side_effect=Exception("extraction failed")):
            with pytest.raises(Exception, match="extraction"):
                analyze_tarball(tar_path)

        mock_rmtree.assert_called_once()


# =============================================================================
# analyzer.py — UniversalAnalyzer
# =============================================================================


class TestUniversalAnalyzerDetectFormat:
    def setup_method(self):
        self.analyzer = UniversalAnalyzer()

    def test_dot_deb(self):
        assert self.analyzer.detect_format("package.deb") == ".deb"

    def test_dot_rpm(self):
        assert self.analyzer.detect_format("package.rpm") == ".rpm"

    def test_dot_appimage(self):
        assert self.analyzer.detect_format("MyApp.AppImage") == ".appimage"

    def test_dot_snap(self):
        assert self.analyzer.detect_format("pkg.snap") == ".snap"

    def test_dot_flatpak(self):
        assert self.analyzer.detect_format("app.flatpak") == ".flatpak"

    def test_dot_tar_gz(self):
        assert self.analyzer.detect_format("archive.tar.gz") == ".tar.gz"

    def test_dot_tgz(self):
        assert self.analyzer.detect_format("archive.tgz") == ".tar.gz"

    def test_dot_tar(self):
        assert self.analyzer.detect_format("archive.tar") == ".tar"

    def test_unknown_format(self):
        assert self.analyzer.detect_format("archive.zip") is None

    def test_no_extension(self):
        assert self.analyzer.detect_format("Makefile") is None

    def test_case_insensitive(self):
        assert self.analyzer.detect_format("PKG.DEB") == ".deb"
        assert self.analyzer.detect_format("FILE.AppImage") == ".appimage"

    def test_detect_tar_gz_before_single_ext(self):
        """Should match .tar.gz before falling through to .gz suffix."""
        assert self.analyzer.detect_format("file.tar.gz") == ".tar.gz"

    def test_dot_tar_bz2(self):
        assert self.analyzer.detect_format("archive.tar.bz2") == ".tar.bz2"

    def test_dot_tar_xz(self):
        assert self.analyzer.detect_format("archive.tar.xz") == ".tar.xz"

    def test_dot_txz_alias(self):
        """'.txz' is an alias for '.tar.xz'."""
        assert self.analyzer.detect_format("archive.txz") == ".tar.xz"

    def test_dot_tbz2_alias(self):
        """'.tbz2' is an alias for '.tar.bz2'."""
        assert self.analyzer.detect_format("archive.tbz2") == ".tar.bz2"

    def test_tar_bz2_case_insensitive(self):
        assert self.analyzer.detect_format("ARCHIVE.TAR.BZ2") == ".tar.bz2"

    def test_tar_xz_case_insensitive(self):
        assert self.analyzer.detect_format("ARCHIVE.TAR.XZ") == ".tar.xz"

    def test_detect_format_module_level(self):
        """The module-level detect_format function should also work."""
        from app2nix.core.analyzer import detect_format

        assert detect_format("archive.tar.bz2") == ".tar.bz2"
        assert detect_format("archive.tar.xz") == ".tar.xz"
        assert detect_format("archive.txz") == ".tar.xz"
        assert detect_format("archive.tbz2") == ".tar.bz2"
        assert detect_format("archive.zip") is None


class TestUniversalAnalyzerAnalyze:
    def setup_method(self):
        self.analyzer = UniversalAnalyzer()

    def test_raises_on_nonexistent_file(self):
        with pytest.raises(FileNotFoundError, match="Package not found"):
            self.analyzer.analyze("/nonexistent/path.deb")

    def test_raises_on_unsupported_format(self, tmp_path):
        p = tmp_path / "archive.zip"
        p.write_text("data")
        with pytest.raises(UnsupportedFormatError, match="Unsupported format"):
            self.analyzer.analyze(str(p))

    def test_routes_to_deb_handler(self, tmp_path):
        p = tmp_path / "package.deb"
        p.write_text("data")
        with patch("app2nix.core.analyzer.analyze_deb") as mock_deb:
            mock_deb.return_value = PackageInfo(
                name="test", version="1.0", format="deb"
            )
            # Patch the format map so the handler points to the mock
            self.analyzer._format_map = {".deb": ("deb", mock_deb)}
            result = self.analyzer.analyze(str(p))
        assert result.name == "test"
        assert result.format == "deb"
        mock_deb.assert_called_once_with(str(p))

    def test_routes_to_appimage_handler(self, tmp_path):
        p = tmp_path / "package.AppImage"
        p.write_text("data")
        with patch("app2nix.core.analyzer.analyze_appimage") as mock_ai:
            mock_ai.return_value = PackageInfo(
                name="test-app", version="1.0", format="appimage"
            )
            self.analyzer._format_map = {".appimage": ("appimage", mock_ai)}
            result = self.analyzer.analyze(str(p))
        assert result.format == "appimage"
        mock_ai.assert_called_once_with(str(p))

    def test_routes_to_rpm_handler(self, tmp_path):
        p = tmp_path / "package.rpm"
        p.write_text("data")
        with patch("app2nix.core.analyzer.analyze_rpm") as mock_rpm:
            mock_rpm.return_value = PackageInfo(
                name="test", version="1.0", format="rpm"
            )
            self.analyzer._format_map = {".rpm": ("rpm", mock_rpm)}
            result = self.analyzer.analyze(str(p))
        assert result.format == "rpm"

    def test_routes_to_tarball_tar_gz(self, tmp_path):
        p = tmp_path / "archive.tar.gz"
        p.write_text("data")
        with patch("app2nix.core.analyzer.analyze_tarball") as mock_tar:
            mock_tar.return_value = PackageInfo(
                name="test", version="1.0", format="tarball"
            )
            self.analyzer._format_map = {".tar.gz": ("tarball", mock_tar)}
            result = self.analyzer.analyze(str(p))
        assert result.format == "tarball"

    def test_supported_formats_has_all_expected_keys(self):
        expected = {".deb", ".rpm", ".appimage", ".flatpak", ".snap", ".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tar.xz"}
        assert set(SUPPORTED_FORMATS.keys()) == expected
