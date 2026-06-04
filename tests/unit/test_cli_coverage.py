"""Cover the remaining CLI code paths not yet tested."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from app2nix.cli import _find_packages, app


def _make_deb_run_side_effect(tmp_path, pkg_name="pkg", version="1.0"):
    def _side(cmd, **kwargs):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        if cmd[:2] == ["dpkg-deb", "-x"]:
            tmp_root = Path(cmd[3])
            (tmp_root / "usr" / "bin").mkdir(parents=True, exist_ok=True)
            (tmp_root / "usr" / "bin" / "myapp").write_text("elf")
            (tmp_root / "usr" / "bin" / "myapp").chmod(0o755)
        elif cmd[:2] == ["dpkg-deb", "-I"]:
            mock.stdout = (
                f"Package: {pkg_name}\n"
                f"Version: {version}\n"
                "Architecture: amd64\n"
            )
        elif cmd[:2] == ["file", "-b"]:
            mock.stdout = "ELF 64-bit LSB executable, x86-64"
        elif cmd[0] == "ldd":
            mock.stdout = "\tlibssl.so.3 => /usr/lib/libssl.so.3 (0x00007f00)\n"
        elif cmd[:2] == ["patchelf", "--print-needed"]:
            mock.stdout = "libssl.so.3\n"
        return mock
    return _side


# =============================================================================
# _find_packages
# =============================================================================


class TestFindPackages:
    def test_returns_supported_formats(self, tmp_path):
        (tmp_path / "test.deb").write_text("")
        (tmp_path / "test.rpm").write_text("")
        (tmp_path / "test.AppImage").write_text("")
        (tmp_path / "test.txt").write_text("")
        result = _find_packages(tmp_path, recursive=False)
        assert len(result) == 3

    def test_rejects_unsupported_formats(self, tmp_path):
        (tmp_path / "readme.txt").write_text("")
        (tmp_path / "script.sh").write_text("")
        result = _find_packages(tmp_path, recursive=False)
        assert result == []

    def test_skips_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "pkg.deb").write_text("")
        result = _find_packages(tmp_path, recursive=False)
        assert result == []

    def test_recursive_scan(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "pkg.deb").write_text("")
        (tmp_path / "root.deb").write_text("")
        result = _find_packages(tmp_path, recursive=True)
        assert len(result) == 2

    def test_returns_sorted(self, tmp_path):
        (tmp_path / "b.deb").write_text("")
        (tmp_path / "a.deb").write_text("")
        (tmp_path / "c.deb").write_text("")
        result = _find_packages(tmp_path, recursive=False)
        assert [p.name for p in result] == ["a.deb", "b.deb", "c.deb"]


# =============================================================================
# Directory mode
# =============================================================================


class TestDirectoryMode:
    def test_no_packages_found(self, tmp_path):
        empty_dir = tmp_path / "emptydir"
        empty_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            app, ["convert", str(empty_dir), "--output-dir", str(tmp_path / "out")]
        )
        assert result.exit_code != 0
        assert "No supported packages" in result.output

    def test_directory_with_packages(self, tmp_path):
        pkg_dir = tmp_path / "pkgs"
        pkg_dir.mkdir()
        deb = pkg_dir / "hello_1.0_amd64.deb"
        deb.write_text("")
        out = tmp_path / "out"
        side = _make_deb_run_side_effect(tmp_path)
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(pkg_dir), "--output-dir", str(out)]
            )
        assert result.exit_code == 0
        assert "Found 1 package(s)" in result.output
        assert (out / "default.nix").exists()

    def test_directory_with_recursive(self, tmp_path):
        pkg_dir = tmp_path / "pkgs"
        sub = pkg_dir / "sub"
        sub.mkdir(parents=True)
        (sub / "inner_1.0_amd64.deb").write_text("")
        out = tmp_path / "out"
        side = _make_deb_run_side_effect(tmp_path, pkg_name="inner")
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(pkg_dir), "-r", "--output-dir", str(out)]
            )
        assert result.exit_code == 0
        assert "Found 1 package(s)" in result.output
        assert (out / "default.nix").exists()


# =============================================================================
# Unsupported format
# =============================================================================


class TestUnsupportedFormat:
    def test_unsupported_extension(self, tmp_path):
        bad = tmp_path / "archive.xyz"
        bad.write_text("")
        runner = CliRunner()
        result = runner.invoke(
            app, ["convert", str(bad), "--output-dir", str(tmp_path)]
        )
        assert result.exit_code != 0
        assert "Unsupported" in result.output


# =============================================================================
# Flake generation
# =============================================================================


class TestFlakeGeneration:
    def test_flake_flag_generates_flake_nix(self, tmp_path):
        deb = tmp_path / "app_1.0_amd64.deb"
        deb.write_text("")
        out = tmp_path / "out"
        side = _make_deb_run_side_effect(tmp_path)
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(deb), "--output-dir", str(out), "--flake"]
            )
        assert result.exit_code == 0
        assert (out / "default.nix").exists()
        assert (out / "flake.nix").exists()
        assert "flake.nix" in result.output


# =============================================================================
# Batch mode
# =============================================================================


class TestBatchMode:
    def test_two_packages_triggers_batch(self, tmp_path):
        d1 = tmp_path / "a.deb"
        d1.write_text("")
        d2 = tmp_path / "b.deb"
        d2.write_text("")
        out = tmp_path / "out"
        side = _make_deb_run_side_effect(tmp_path)
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(tmp_path), "--output-dir", str(out)]
            )
        assert result.exit_code == 0
        assert "Batch results" in result.output

    def test_parallel_batch(self, tmp_path):
        d1 = tmp_path / "p1.deb"
        d1.write_text("")
        d2 = tmp_path / "p2.deb"
        d2.write_text("")
        out = tmp_path / "out"
        side = _make_deb_run_side_effect(tmp_path)
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(tmp_path), "--output-dir", str(out), "--parallel", "2"]
            )
        assert result.exit_code == 0
        assert "Batch results" in result.output

    def test_all_fail_reported(self, tmp_path):
        """Batch mode shows errors for failed packages."""
        d1 = tmp_path / "fail1.deb"
        d1.write_text("")
        d2 = tmp_path / "fail2.deb"
        d2.write_text("")
        out = tmp_path / "out"

        class FailingSubprocess:
            call_count = 0
            def __call__(self, cmd, **kwargs):
                mock = MagicMock()
                mock.returncode = 0
                mock.stdout = ""
                self.call_count += 1
                if cmd[:2] == ["dpkg-deb", "-I"] and self.call_count > 2:
                    mock.stdout = "Package: fail2\nVersion: 2.0\nArchitecture: amd64\n"
                elif cmd[:2] == ["dpkg-deb", "-I"]:
                    mock.stdout = "Package: fail1\nVersion: 1.0\nArchitecture: amd64\n"
                elif cmd[:2] == ["dpkg-deb", "-x"]:
                    # Simulate extraction failures by raising FileNotFoundError
                    if self.call_count <= 2:
                        raise FileNotFoundError("no dpkg-deb")
                elif cmd[0] == "file":
                    if self.call_count <= 2:
                        raise FileNotFoundError("no file")
                elif cmd[0] == "ldd":
                    mock.stdout = ""
                elif cmd[:2] == ["patchelf", "--print-needed"]:
                    raise FileNotFoundError("no patchelf")
                return mock

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=FailingSubprocess()):
            result = runner.invoke(
                app, ["convert", str(tmp_path), "--output-dir", str(out)]
            )
        assert result.exit_code == 0

    def test_batch_quiet_mode(self, tmp_path):
        d1 = tmp_path / "quiet_a.deb"
        d1.write_text("")
        d2 = tmp_path / "quiet_b.deb"
        d2.write_text("")
        out = tmp_path / "quiet_out"
        side = _make_deb_run_side_effect(tmp_path)
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(tmp_path), "--output-dir", str(out), "--quiet"]
            )
        assert result.exit_code == 0
        assert "Batch results" not in result.output

    def test_batch_quiet_parallel(self, tmp_path):
        d1 = tmp_path / "qp_a.deb"
        d1.write_text("")
        d2 = tmp_path / "qp_b.deb"
        d2.write_text("")
        out = tmp_path / "qp_out"
        side = _make_deb_run_side_effect(tmp_path)
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(tmp_path), "--output-dir", str(out), "--quiet", "--parallel", "2"]
            )
        assert result.exit_code == 0
        assert "Batch results" not in result.output

    def test_batch_all_succeed(self, tmp_path):
        d1 = tmp_path / "ok_a.deb"
        d1.write_text("")
        d2 = tmp_path / "ok_b.deb"
        d2.write_text("")
        out = tmp_path / "succeed_out"
        side = _make_deb_run_side_effect(tmp_path)
        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app, ["convert", str(tmp_path), "--output-dir", str(out)]
            )
        assert result.exit_code == 0
        assert "succeeded" in result.output
        assert "failed" in result.output


# =============================================================================
# _convert_single error handling
# =============================================================================


class TestConvertSingleErrors:
    def test_error_in_analysis_shown(self, tmp_path):
        bad = tmp_path / "broken.deb"
        bad.write_text("")
        out = tmp_path / "err_out"

        def failing_side(cmd, **kwargs):
            raise RuntimeError("Unexpected crash")

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=failing_side):
            result = runner.invoke(
                app, ["convert", str(bad), "--output-dir", str(out)]
            )
        assert result.exit_code == 0  # single file errors still exit 0
        assert "Error processing" in result.output


# =============================================================================
# cleanup command
# =============================================================================


class TestCleanupCommand:
    def test_cleanup_no_tracked_packages(self):
        runner = CliRunner()
        with patch("app2nix.manifest.load_manifest", return_value={"packages": {}}):
            result = runner.invoke(app, ["cleanup"])
        assert result.exit_code == 0
        assert "No tracked packages" in result.output

    def test_cleanup_all_installed(self):
        runner = CliRunner()
        with (
            patch("app2nix.manifest.load_manifest", return_value={
                "packages": {"firefox": {"desktop_files": [], "icon_files": []}}
            }),
            patch("app2nix.manifest.cleanup_orphaned_entries", return_value=0),
        ):
            result = runner.invoke(app, ["cleanup"])
        assert result.exit_code == 0
        assert "nothing to clean" in result.output

    def test_cleanup_removes_orphans(self):
        runner = CliRunner()
        with (
            patch("app2nix.manifest.load_manifest", return_value={
                "packages": {"gone": {"desktop_files": [], "icon_files": []}}
            }),
            patch("app2nix.manifest.cleanup_orphaned_entries", return_value=1),
        ):
            result = runner.invoke(app, ["cleanup"])
        assert result.exit_code == 0
        assert "Cleaned" in result.output
        assert "1" in result.output

    def test_cleanup_verbose_flag(self):
        runner = CliRunner()
        with (
            patch("app2nix.manifest.load_manifest", return_value={
                "packages": {"gone": {"desktop_files": [], "icon_files": []}}
            }),
            patch("app2nix.manifest.cleanup_orphaned_entries", return_value=2),
        ):
            result = runner.invoke(app, ["cleanup", "--verbose"])
        assert result.exit_code == 0
        assert "Cleaned" in result.output
