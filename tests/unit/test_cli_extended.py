"""
Extra CLI tests covering the remaining uncovered code paths in cli.py:

  1. ``--print-deps`` flag  (deps table with resolved + unresolved)
  2. ``--json`` with dependencies  (json_result construction with deps)
  3. Validation warning panel  (``--validate`` + validation error)
  4. ``--no-validate`` flag (skip validation entirely)
  5. Unresolved deps panel
  6. ``--verbose`` flag
  7. Package not found error
  8. ``gui()`` ImportError path
  9. Batch conversion (multiple packages)
 10. _resolve_packages helper
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from app2nix.cli import _find_packages, app

# =============================================================================
# Helpers
# =============================================================================


class _FakeModule:
    """Minimal fake module to simulate imports for patching."""
    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)


def _make_deb_run_side_effect(tmp_path, pkg_name="cli-test", version="1.0"):
    """Build a side_effect for subprocess.run that simulates dpkg-deb."""
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
            mock.stdout = "libssl.so.3\nlibunknown_xyz.so\n"

        return mock

    return _side


def _make_validator_side_effect(valid: bool = True, err: str | None = None):
    """Build a side_effect for subprocess.run that simulates nix-instantiate."""
    def _side(cmd, **kwargs):
        mock = MagicMock()
        mock.returncode = 0 if valid else 1
        mock.stderr = err or ""
        mock.stdout = ""
        return mock
    return _side


# =============================================================================
# Package not found
# =============================================================================


class TestPackageNotFound:
    """``app2nix convert nonexistent.deb``"""

    def test_package_not_found_shows_error(self, tmp_path):
        """When the package file doesn't exist, show an error and exit."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["convert", str(tmp_path / "nonexistent.deb"), "--output-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "Not found" in result.output


# =============================================================================
# --print-deps
# =============================================================================


class TestPrintDeps:
    """``app2nix convert pkg.deb --print-deps``"""

    def test_print_deps_shows_resolved_deps(self, tmp_path):
        """``--print-deps`` prints a table with resolved dependencies."""
        deb_file = tmp_path / "test-app_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--print-deps"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        # Should show the deps table with resolved libs
        assert "openssl" in result.output  # ssl → openssl
        # Should NOT generate any output files
        assert not (out_dir / "default.nix").exists()
        assert not (out_dir / "flake.nix").exists()

    def test_print_deps_shows_unresolved(self, tmp_path):
        """``--print-deps`` shows unresolved deps with "unknown"."""
        deb_file = tmp_path / "unknown-deps_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "out2"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--print-deps"],
            )

        assert result.exit_code == 0
        # unknown_xyz is not in DEP_MAP, should show as unknown
        assert "unknown_xyz" in result.output or "unknown" in result.output


# =============================================================================
# --json with dependencies
# =============================================================================


class TestJsonWithDeps:
    """``app2nix convert pkg.deb --json`` with actual dependencies."""

    def test_json_with_deps_includes_nix_deps(self, tmp_path):
        """JSON output should include resolved nixpkg names in 'dependencies'."""
        deb_file = tmp_path / "json-deps_2.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "json-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path, pkg_name="json-deps", version="2.0")

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--json"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        json_file = out_dir / "json-deps.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert data["name"] == "json-deps"
        assert data["version"] == "2.0"
        # Should have deps (ssl → openssl or similar)
        assert len(data["dependencies"]) > 0
        assert len(data["libraries"]) > 0
        assert "openssl" in data["dependencies"]


# =============================================================================
# Validation warning
# =============================================================================


class TestValidation:
    """Validation flag behavior."""

    def test_validation_warning_on_parse_failure(self, tmp_path):
        """When nix-instantiate fails, a validation warning should be shown."""
        deb_file = tmp_path / "bad-nix_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "val-out"
        out_dir.mkdir()

        # Side effect for the analyzer (dpkg-deb, file, ldd, patchelf)
        deb_side = _make_deb_run_side_effect(tmp_path, pkg_name="bad-nix")
        # Side effect for the validator (nix-instantiate — return failure)
        val_side = _make_validator_side_effect(valid=False, err="syntax error at line 3")

        def combined_side(cmd, **kwargs):
            if cmd[0] == "nix-instantiate":
                return val_side(cmd, **kwargs)
            return deb_side(cmd, **kwargs)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=combined_side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--validate"],
            )

        assert result.exit_code == 0
        # Should show validation warning
        assert "Validation" in result.output or "validation" in result.output
        # default.nix should still be generated
        assert (out_dir / "default.nix").exists()

    def test_no_validate_skips_warning_panel(self, tmp_path):
        """With ``--no-validate``, the validation warning panel is not shown.

        Note: ``NixGenerator.validate()`` is still called internally by
        ``generate_default_nix()`` — the ``--no-validate`` flag only
        prevents the warning panel from being displayed.
        """
        deb_file = tmp_path / "no-val_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "no-val-out"
        out_dir.mkdir()

        # Simulate a validation error so we can verify the panel is hidden
        deb_side = _make_deb_run_side_effect(tmp_path, pkg_name="no-val")
        val_side = _make_validator_side_effect(valid=False, err="syntax error")

        def combined_side(cmd, **kwargs):
            if cmd[0] == "nix-instantiate":
                return val_side(cmd, **kwargs)
            return deb_side(cmd, **kwargs)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=combined_side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--no-validate"],
            )

        assert result.exit_code == 0
        assert (out_dir / "default.nix").exists()
        # The validation warning panel should NOT be shown
        assert "Validation warning" not in result.output
        # But since the generator still validates internally, nix-instantiate
        # was called — the flag just controls the display


# =============================================================================
# Unresolved deps panel
# =============================================================================


class TestUnresolvedDeps:
    """Unresolved dependencies panel."""

    def test_unresolved_deps_panel_shown(self, tmp_path):
        """When there are unresolved deps, a panel should be printed."""
        deb_file = tmp_path / "unresolved_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "unres-out"
        out_dir.mkdir()

        deb_side = _make_deb_run_side_effect(tmp_path, pkg_name="unresolved")

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=deb_side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0
        # The dep "unknown_xyz" should be unresolved
        assert "unresolved" in result.output.lower()
        assert (out_dir / "default.nix").exists()


# =============================================================================
# --verbose
# =============================================================================


class TestVerbose:
    """``--verbose`` flag prints package info panel."""

    def test_verbose_shows_package_info(self, tmp_path):
        """With ``--verbose``, a Package Info panel should be printed."""
        deb_file = tmp_path / "verbose_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "verbose-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path, pkg_name="verbose")

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--verbose"],
            )

        assert result.exit_code == 0
        assert "Package Info" in result.output
        assert "verbose" in result.output
        assert "1.0" in result.output
        assert "deb" in result.output


# =============================================================================
# gui() ImportError path
# =============================================================================


class TestGuiCommand:
    """``app2nix gui`` command error handling."""

    def test_gui_import_error_shows_message(self):
        """When PyQt6 is missing, the gui command should show an error."""
        runner = CliRunner()

        # Force ImportError by making app2nix.gui unimportable
        with patch.dict(sys.modules, {"app2nix.gui": None}):
            result = runner.invoke(app, ["gui"])

        assert result.exit_code != 0
        assert "PyQt6" in result.output

    def test_gui_success_calls_run_gui(self):
        """When PyQt6 IS available, run_gui should be called."""
        fake_run_gui = MagicMock()
        fake_gui_module = _FakeModule(run_gui=fake_run_gui)

        runner = CliRunner()
        with patch.dict(sys.modules, {"app2nix.gui": fake_gui_module}):
            result = runner.invoke(app, ["gui"])

        assert result.exit_code == 0
        fake_run_gui.assert_called_once()


# =============================================================================
# serve command
# =============================================================================


class TestServeCommand:
    """``app2nix serve`` command."""

    def test_serve_starts_uvicorn(self):
        """The serve command should call uvicorn.run with correct args."""
        fake_uvicorn = _FakeModule(run=MagicMock())

        runner = CliRunner()
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "9000"])

        assert result.exit_code == 0
        fake_uvicorn.run.assert_called_once_with(
            "app2nix.server:app",
            host="127.0.0.1",
            port=9000,
            reload=False,
        )

    def test_serve_with_reload(self):
        """The --reload flag should be passed to uvicorn.run."""
        fake_uvicorn = _FakeModule(run=MagicMock())

        runner = CliRunner()
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            result = runner.invoke(app, ["serve", "--reload"])

        assert result.exit_code == 0
        fake_uvicorn.run.assert_called_once_with(
            "app2nix.server:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
        )


# =============================================================================
# --flake flag
# =============================================================================


class TestFlakeFlag:
    """``app2nix convert pkg.deb --flake`` generates both default.nix and flake.nix."""

    def test_flake_generates_flake_nix(self, tmp_path):
        """With ``--flake``, a flake.nix file should also be written."""
        deb_file = tmp_path / "flake-test_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "flake-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path, pkg_name="flake-test")

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "default.nix").exists()
        assert (out_dir / "flake.nix").exists()
        # Rich may wrap the filename — check the file exists instead of output text
        assert "Generated" in result.output

    def test_no_flake_by_default(self, tmp_path):
        """Without ``--flake``, only default.nix is generated."""
        deb_file = tmp_path / "no-flake_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "no-flake-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path, pkg_name="no-flake")

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0
        assert (out_dir / "default.nix").exists()
        assert not (out_dir / "flake.nix").exists()


# =============================================================================
# convert — full successful flow
# =============================================================================


class TestConvertFullFlow:
    """Full convert command with all defaults."""

    def test_convert_creates_default_nix(self, tmp_path):
        """Basic convert should produce a valid default.nix."""
        deb_file = tmp_path / "basic_1.0_amd64.deb"
        deb_file.write_text("fake deb")
        out_dir = tmp_path / "basic-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path, pkg_name="basic")

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb_file), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0
        nix_file = out_dir / "default.nix"
        assert nix_file.exists()
        content = nix_file.read_text()
        assert "mkDerivation" in content
        assert "basic" in content.lower()


# =============================================================================
# Batch conversion (multiple packages)
# =============================================================================


class TestBatchConversion:
    """Batch mode: ``app2nix convert pkg1.deb pkg2.rpm``"""

    def test_batch_two_debs(self, tmp_path):
        """Two deb files should each get their own subdirectory."""
        deb1 = tmp_path / "alpha_1.0_amd64.deb"
        deb1.write_text("fake deb 1")
        deb2 = tmp_path / "beta_2.0_amd64.deb"
        deb2.write_text("fake deb 2")
        out_dir = tmp_path / "batch-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                [
                    "convert",
                    str(deb1), str(deb2),
                    "--output-dir", str(out_dir),
                ],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "2 package(s)" in result.output
        # Each package gets its own subdirectory
        assert (out_dir / "alpha_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "beta_2.0_amd64" / "default.nix").exists()
        # Summary table should appear
        assert "Batch results" in result.output
        assert "2 succeeded" in result.output
        assert "0 failed" in result.output

    def test_batch_with_glob_pattern(self, tmp_path):
        """Glob pattern ``*.deb`` should expand to multiple packages."""
        for name in ("app1_1.0_amd64.deb", "app2_1.0_amd64.deb", "app3_1.0_amd64.deb"):
            (tmp_path / name).write_text("fake deb")
        out_dir = tmp_path / "glob-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                [
                    "convert",
                    str(tmp_path / "*.deb"),
                    "--output-dir", str(out_dir),
                ],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "3 package(s)" in result.output
        assert "3 succeeded" in result.output
        # Each gets a subdirectory
        assert (out_dir / "app1_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "app2_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "app3_1.0_amd64" / "default.nix").exists()

    def test_batch_partial_failure(self, tmp_path):
        """Batch with one non-existent file should fail with not-found error."""
        good = tmp_path / "good_1.0_amd64.deb"
        good.write_text("fake deb")
        bad = tmp_path / "nonexistent.deb"
        out_dir = tmp_path / "partial-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                [
                    "convert",
                    str(good), str(bad),
                    "--output-dir", str(out_dir),
                ],
            )

        assert result.exit_code != 0
        assert "Not found" in result.output

    def test_batch_with_flake_flag(self, tmp_path):
        """--flake should apply to all packages in batch mode."""
        deb1 = tmp_path / "a_1.0_amd64.deb"
        deb1.write_text("fake deb 1")
        deb2 = tmp_path / "b_1.0_amd64.deb"
        deb2.write_text("fake deb 2")
        out_dir = tmp_path / "flake-batch"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                [
                    "convert",
                    str(deb1), str(deb2),
                    "--output-dir", str(out_dir),
                    "--flake",
                ],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "a_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "a_1.0_amd64" / "flake.nix").exists()
        assert (out_dir / "b_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "b_1.0_amd64" / "flake.nix").exists()

    def test_batch_no_matching_glob(self, tmp_path):
        """Glob with no matches should error."""
        out_dir = tmp_path / "empty-out"
        out_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "convert",
                str(tmp_path / "*.xyz"),
                "--output-dir", str(out_dir),
            ],
        )

        assert result.exit_code != 0
        assert "No matching package files found" in result.output


# =============================================================================
# Batch conversion — multi-format (RPM, tarball, AppImage)
# =============================================================================


def _make_combined_rpm_deb_tar_side_effect(tmp_path):
    """Build combined side effects for deb + rpm + tarball batch tests."""
    _run_deb = _make_deb_run_side_effect(tmp_path)
    _run_rpm, _check_rpm = _make_rpm_run_side_effect(tmp_path)
    _run_tar = _make_tarball_run_side_effect(tmp_path)

    def combined_run(cmd, **kwargs):
        if cmd[0] in ("dpkg-deb",):
            return _run_deb(cmd, **kwargs)
        elif cmd[0] in ("rpm",):
            return _run_rpm(cmd, **kwargs)
        elif "tar" in cmd or cmd[0] == "tar":
            return _run_tar(cmd, **kwargs)
        else:
            return _run_deb(cmd, **kwargs)

    def combined_check_output(cmd, **kwargs):
        m = _run_rpm(cmd, **kwargs)
        if m.returncode != 0:
            raise subprocess.CalledProcessError(m.returncode, cmd)
        return m.stdout

    return combined_run, combined_check_output


def _make_rpm_run_side_effect(tmp_path, pkg_name="rpm-test", version="1.0"):
    """Build a side_effect for subprocess that simulates RPM analysis.

    RPM uses ``subprocess.check_output`` (not ``subprocess.run``) for
    ``rpm -qp --queryformat`` and ``rpm -qp --requires``.
    """
    def _run(cmd, **kwargs):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        if cmd[:2] == ["rpm", "-qp"] and "--queryformat" in cmd:
            mock.stdout = f"{pkg_name}\t{version}\tx86_64\n"
        elif cmd[:2] == ["rpm", "-qp"] and "--requires" in cmd:
            mock.stdout = "libssl.so.3\nlibz.so.1\n"
        elif cmd[:2] == ["file", "-b"]:
            mock.stdout = "ELF 64-bit LSB executable, x86-64"
        elif cmd[:2] == ["patchelf", "--print-needed"]:
            mock.stdout = "libssl.so.3\nlibunknown_xyz.so\n"
        return mock

    def _check_output(cmd, **kwargs):
        m = _run(cmd, **kwargs)
        if m.returncode != 0:
            raise subprocess.CalledProcessError(m.returncode, cmd)
        return m.stdout

    return _run, _check_output


def _make_tarball_run_side_effect(tmp_path):
    """Build a side_effect for subprocess.run that simulates tarball extraction.

    The tarball analyzer calls ``subprocess.run(['tar', ...])``,
    then ``file -b`` and ``patchelf --print-needed``.
    """
    def _side(cmd, **kwargs):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        if "tar" in cmd:
            mock.returncode = 0
        elif cmd[:2] == ["file", "-b"]:
            mock.stdout = "ELF 64-bit LSB executable, x86-64"
        elif cmd[:2] == ["patchelf", "--print-needed"]:
            mock.stdout = "libssl.so.3\nlibz.so.1\n"
        return mock
    return _side


class TestBatchMultiFormat:
    """Batch mode with non-deb formats: RPM, tarball, AppImage."""

    def test_batch_rpm_conversion(self, tmp_path):
        """Two RPM files should each get their own subdirectory."""
        rpm1 = tmp_path / "alpha-1.0.x86_64.rpm"
        rpm1.write_text("fake rpm 1")
        rpm2 = tmp_path / "beta-2.0.x86_64.rpm"
        rpm2.write_text("fake rpm 2")
        out_dir = tmp_path / "rpm-batch"
        out_dir.mkdir()

        _run_side, _check_output = _make_rpm_run_side_effect(tmp_path)

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=_run_side),
            patch.object(subprocess, "check_output", side_effect=_check_output),
        ):
            result = runner.invoke(
                app,
                ["convert", str(rpm1), str(rpm2), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "2 package(s)" in result.output
        assert "2 succeeded" in result.output
        assert (out_dir / "alpha-1.0.x86_64" / "default.nix").exists()
        assert (out_dir / "beta-2.0.x86_64" / "default.nix").exists()

    def test_batch_tarball_conversion(self, tmp_path):
        """Multiple tarballs should each get their own subdirectory."""
        tar1 = tmp_path / "app1-1.0.tar.gz"
        tar1.write_text("fake tar 1")
        tar2 = tmp_path / "app2-2.0.tar.xz"
        tar2.write_text("fake tar 2")
        tar3 = tmp_path / "app3-3.0.tar.bz2"
        tar3.write_text("fake tar 3")
        out_dir = tmp_path / "tar-batch"
        out_dir.mkdir()

        tar_side = _make_tarball_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=tar_side):
            result = runner.invoke(
                app,
                ["convert", str(tar1), str(tar2), str(tar3), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "3 package(s)" in result.output
        assert "3 succeeded" in result.output
        # Each tarball gets its own subdirectory
        assert (out_dir / "app1-1.0.tar" / "default.nix").exists()
        assert (out_dir / "app2-2.0.tar" / "default.nix").exists()
        assert (out_dir / "app3-3.0.tar" / "default.nix").exists()

    def test_batch_mixed_formats(self, tmp_path):
        """Mix .deb, .rpm, and .tar.gz in a single batch command."""
        deb = tmp_path / "my-deb_1.0_amd64.deb"
        deb.write_text("fake deb")
        rpm = tmp_path / "my-rpm-1.0.x86_64.rpm"
        rpm.write_text("fake rpm")
        tar = tmp_path / "my-tar-1.0.tar.gz"
        tar.write_text("fake tar")
        out_dir = tmp_path / "mixed-batch"
        out_dir.mkdir()

        combined_run, combined_check = _make_combined_rpm_deb_tar_side_effect(tmp_path)

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=combined_run),
            patch.object(subprocess, "check_output", side_effect=combined_check),
        ):
            result = runner.invoke(
                app,
                ["convert", str(deb), str(rpm), str(tar), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "3 package(s)" in result.output
        assert "3 succeeded" in result.output
        assert (out_dir / "my-deb_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "my-rpm-1.0.x86_64" / "default.nix").exists()
        assert (out_dir / "my-tar-1.0.tar" / "default.nix").exists()

    def test_batch_deb_rpm_tar_glob(self, tmp_path):
        """Glob matching .deb, .rpm, and .tar.gz files."""
        (tmp_path / "foo.deb").write_text("deb")
        (tmp_path / "bar.rpm").write_text("rpm")
        (tmp_path / "baz.tar.gz").write_text("tar")
        out_dir = tmp_path / "glob-mixed"
        out_dir.mkdir()

        combined_run, combined_check = _make_combined_rpm_deb_tar_side_effect(tmp_path)

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=combined_run),
            patch.object(subprocess, "check_output", side_effect=combined_check),
        ):
            result = runner.invoke(
                app,
                ["convert", str(tmp_path / "*.deb"), str(tmp_path / "*.rpm"), str(tmp_path / "*.tar.*"), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "3 succeeded" in result.output
        assert (out_dir / "foo" / "default.nix").exists()
        assert (out_dir / "bar" / "default.nix").exists()
        # Path('baz.tar.gz').stem == 'baz.tar' (Python only strips last suffix)
        assert (out_dir / "baz.tar" / "default.nix").exists()

    def test_batch_rpm_with_flake(self, tmp_path):
        """--flake flag should work with RPM batch conversion."""
        rpm1 = tmp_path / "alpha-1.0.x86_64.rpm"
        rpm1.write_text("fake rpm 1")
        rpm2 = tmp_path / "beta-2.0.x86_64.rpm"
        rpm2.write_text("fake rpm 2")
        out_dir = tmp_path / "rpm-flake"
        out_dir.mkdir()

        _run_side, _check_output = _make_rpm_run_side_effect(tmp_path)

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=_run_side),
            patch.object(subprocess, "check_output", side_effect=_check_output),
        ):
            result = runner.invoke(
                app,
                ["convert", str(rpm1), str(rpm2), "--output-dir", str(out_dir), "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "alpha-1.0.x86_64" / "default.nix").exists()
        assert (out_dir / "alpha-1.0.x86_64" / "flake.nix").exists()
        assert (out_dir / "beta-2.0.x86_64" / "default.nix").exists()
        assert (out_dir / "beta-2.0.x86_64" / "flake.nix").exists()

    def test_batch_two_tarballs_succeed(self, tmp_path):
        """Batch with two valid tarballs should succeed for both."""
        good = tmp_path / "good-1.0.tar.gz"
        good.write_text("fake tar")
        good2 = tmp_path / "good2-1.0.tar.gz"
        good2.write_text("fake tar")
        out_dir = tmp_path / "tar-succeed"
        out_dir.mkdir()

        tar_side = _make_tarball_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=tar_side):
            result = runner.invoke(
                app,
                ["convert", str(good), str(good2), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "2 succeeded" in result.output
        assert (out_dir / "good-1.0.tar" / "default.nix").exists()
        assert (out_dir / "good2-1.0.tar" / "default.nix").exists()

    def test_batch_all_formats_glob(self, tmp_path):
        """Glob ``*.tar.*`` should match tar.gz, tar.xz, and tar.bz2."""
        (tmp_path / "foo.tar.gz").write_text("tar")
        (tmp_path / "bar.tar.xz").write_text("tar")
        (tmp_path / "baz.tar.bz2").write_text("tar")
        out_dir = tmp_path / "tar-glob"
        out_dir.mkdir()

        tar_side = _make_tarball_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=tar_side):
            result = runner.invoke(
                app,
                ["convert", str(tmp_path / "*.tar.*"), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "3 package(s)" in result.output
        assert "3 succeeded" in result.output
        assert (out_dir / "foo.tar" / "default.nix").exists()
        assert (out_dir / "bar.tar" / "default.nix").exists()
        assert (out_dir / "baz.tar" / "default.nix").exists()

    def test_batch_appimage_conversion(self, tmp_path):
        """Two AppImage files should each get their own subdirectory."""
        from app2nix.core.analyzer import SUPPORTED_FORMATS
        from app2nix.models import PackageInfo

        ai1 = tmp_path / "alpha.AppImage"
        ai1.write_text("fake appimage 1")
        ai2 = tmp_path / "beta.AppImage"
        ai2.write_text("fake appimage 2")
        out_dir = tmp_path / "ai-batch"
        out_dir.mkdir()

        def mock_analyze(path):
            name = Path(path).stem
            return PackageInfo(name=name, version="1.0", architecture="x86_64", format="appimage", dependencies=["ssl", "z"], executables=[f"usr/bin/{name}"])

        runner = CliRunner()
        with patch.dict(SUPPORTED_FORMATS, {".appimage": ("appimage", mock_analyze)}):
            result = runner.invoke(
                app,
                ["convert", str(ai1), str(ai2), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "2 package(s)" in result.output
        assert "2 succeeded" in result.output
        assert (out_dir / "alpha" / "default.nix").exists()
        assert (out_dir / "beta" / "default.nix").exists()

    def test_batch_deb_rpm_mixed_with_glob(self, tmp_path):
        """Glob matching both .deb and .rpm files in the same directory."""
        (tmp_path / "tool-v1.deb").write_text("deb")
        (tmp_path / "tool-v2.rpm").write_text("rpm")
        out_dir = tmp_path / "deb-rpm-glob"
        out_dir.mkdir()

        combined_run, combined_check = _make_combined_rpm_deb_tar_side_effect(tmp_path)

        runner = CliRunner()
        with (
            patch.object(subprocess, "run", side_effect=combined_run),
            patch.object(subprocess, "check_output", side_effect=combined_check),
        ):
            result = runner.invoke(
                app,
                ["convert", str(tmp_path / "tool-*.*"), "--output-dir", str(out_dir)],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "2 package(s)" in result.output
        assert "2 succeeded" in result.output


# =============================================================================
# --parallel flag
# =============================================================================


class TestParallelFlag:
    """``--parallel N`` flag for concurrent batch conversion."""

    def test_parallel_batch_succeeds(self, tmp_path):
        """With --parallel 2, two deb files should each get their own subdirectory."""
        deb1 = tmp_path / "alpha_1.0_amd64.deb"
        deb1.write_text("fake deb 1")
        deb2 = tmp_path / "beta_2.0_amd64.deb"
        deb2.write_text("fake deb 2")
        out_dir = tmp_path / "parallel-out"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb1), str(deb2), "--output-dir", str(out_dir), "--parallel", "2"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Parallel mode: 2 workers" in result.output
        assert "2 succeeded" in result.output
        assert (out_dir / "alpha_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "beta_2.0_amd64" / "default.nix").exists()
        # Summary table should appear
        assert "Batch results" in result.output

    def test_parallel_with_three_packages(self, tmp_path):
        """With --parallel 3, three packages should all succeed."""
        for i in range(3):
            (tmp_path / f"pkg{i}_1.0_amd64.deb").write_text(f"fake deb {i}")
        out_dir = tmp_path / "parallel-3"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                [
                    "convert",
                    str(tmp_path / "*.deb"),
                    "--output-dir", str(out_dir),
                    "--parallel", "3",
                ],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "3 package(s)" in result.output
        assert "Parallel mode: 3 workers" in result.output
        assert "3 succeeded" in result.output
        for i in range(3):
            assert (out_dir / f"pkg{i}_1.0_amd64" / "default.nix").exists()

    def test_parallel_partial_failure(self, tmp_path):
        """With --parallel 2, one non-existent file should fail with not-found error."""
        good = tmp_path / "good_1.0_amd64.deb"
        good.write_text("fake deb")
        bad = tmp_path / "nonexistent.deb"
        out_dir = tmp_path / "parallel-partial"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(good), str(bad), "--output-dir", str(out_dir), "--parallel", "2"],
            )

        assert result.exit_code != 0
        assert "Not found" in result.output

    def test_parallel_with_flake(self, tmp_path):
        """--parallel with --flake should generate both files."""
        deb1 = tmp_path / "a_1.0_amd64.deb"
        deb1.write_text("fake deb 1")
        deb2 = tmp_path / "b_1.0_amd64.deb"
        deb2.write_text("fake deb 2")
        out_dir = tmp_path / "parallel-flake"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb1), str(deb2), "--output-dir", str(out_dir), "--parallel", "2", "--flake"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert (out_dir / "a_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "a_1.0_amd64" / "flake.nix").exists()
        assert (out_dir / "b_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "b_1.0_amd64" / "flake.nix").exists()

    def test_parallel_1_uses_sequential(self, tmp_path):
        """--parallel 1 should behave identically to sequential mode."""
        deb1 = tmp_path / "x_1.0_amd64.deb"
        deb1.write_text("fake deb")
        deb2 = tmp_path / "y_1.0_amd64.deb"
        deb2.write_text("fake deb")
        out_dir = tmp_path / "parallel-1"
        out_dir.mkdir()

        side = _make_deb_run_side_effect(tmp_path)

        runner = CliRunner()
        with patch.object(subprocess, "run", side_effect=side):
            result = runner.invoke(
                app,
                ["convert", str(deb1), str(deb2), "--output-dir", str(out_dir), "--parallel", "1"],
            )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        # With parallel=1, should NOT show "Parallel mode" message
        assert "Parallel mode" not in result.output
        assert "2 succeeded" in result.output
        assert (out_dir / "x_1.0_amd64" / "default.nix").exists()
        assert (out_dir / "y_1.0_amd64" / "default.nix").exists()


class TestResolvePackages:
    """_resolve_packages helper function."""

    def test_resolve_literal_paths(self, tmp_path):
        """Literal paths are returned in sorted order."""
        from app2nix.cli import _resolve_packages

        (tmp_path / "c.deb").write_text("")
        (tmp_path / "a.deb").write_text("")
        (tmp_path / "b.deb").write_text("")

        result = _resolve_packages([
            str(tmp_path / "c.deb"),
            str(tmp_path / "a.deb"),
            str(tmp_path / "b.deb"),
        ])

        names = [p.name for p in result]
        assert names == ["a.deb", "b.deb", "c.deb"]

    def test_resolve_deduplicates(self, tmp_path):
        """Duplicate paths should appear only once."""
        from app2nix.cli import _resolve_packages

        f = tmp_path / "dup.deb"
        f.write_text("")

        result = _resolve_packages([str(f), str(f)])
        assert len(result) == 1

    def test_resolve_nonexistent_path(self, tmp_path):
        """Non-existent literal paths are included (for error messages)."""
        from app2nix.cli import _resolve_packages

        result = _resolve_packages([str(tmp_path / "missing.deb")])
        assert len(result) == 1
        assert result[0].name == "missing.deb"



# ---------------------------------------------------------------------------
# Directory input tests (issue #12)
# ---------------------------------------------------------------------------


class TestDirectoryInput:
    """Tests for directory input support in app2nix convert."""

    def test_directory_finds_packages(self, tmp_path):
        """Directory with .deb files should find and convert them."""
        pkg_dir = tmp_path / "packages"
        pkg_dir.mkdir()
        (pkg_dir / "a.deb").write_bytes(b"fake")
        (pkg_dir / "b.deb").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("subprocess.run", side_effect=_make_deb_run_side_effect(tmp_path, "pkg", "1.0")):
            result = CliRunner().invoke(app, [
                "convert", str(pkg_dir),
                "--output-dir", str(out_dir),
            ])
        assert result.exit_code == 0
        assert "Found 2 package(s)" in result.output
        assert "succeeded" in result.output

    def test_directory_empty_shows_error(self, tmp_path):
        """Empty directory should show error."""
        pkg_dir = tmp_path / "empty"
        pkg_dir.mkdir()
        result = CliRunner().invoke(app, ["convert", str(pkg_dir)])
        assert result.exit_code == 1
        assert "No supported packages found" in result.output

    def test_directory_skips_non_package_files(self, tmp_path):
        """Non-package files should be skipped silently."""
        pkg_dir = tmp_path / "mixed"
        pkg_dir.mkdir()
        (pkg_dir / "readme.txt").write_text("hello")
        (pkg_dir / "image.png").write_bytes(b"png")
        (pkg_dir / "a.deb").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("subprocess.run", side_effect=_make_deb_run_side_effect(tmp_path, "pkg", "1.0")):
            result = CliRunner().invoke(app, [
                "convert", str(pkg_dir),
                "--output-dir", str(out_dir),
            ])
        assert result.exit_code == 0
        assert "Found 1 package(s)" in result.output

    def test_directory_recursive(self, tmp_path):
        """--recursive should traverse subdirectories."""
        pkg_dir = tmp_path / "packages"
        sub1 = pkg_dir / "sub1"
        sub2 = pkg_dir / "sub2"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        (sub1 / "a.deb").write_bytes(b"fake")
        (sub2 / "b.deb").write_bytes(b"fake")
        (pkg_dir / "readme.txt").write_text("hi")
        out_dir = tmp_path / "out"

        with patch("subprocess.run", side_effect=_make_deb_run_side_effect(tmp_path, "pkg", "1.0")):
            result = CliRunner().invoke(app, [
                "convert", str(pkg_dir),
                "--recursive",
                "--output-dir", str(out_dir),
            ])
        assert result.exit_code == 0
        assert "Found 2 package(s)" in result.output

    def test_directory_non_recursive_skips_subdirs(self, tmp_path):
        """Without --recursive, subdirectories are ignored."""
        pkg_dir = tmp_path / "packages"
        sub = pkg_dir / "sub"
        sub.mkdir(parents=True)
        (sub / "a.deb").write_bytes(b"fake")
        (pkg_dir / "b.deb").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("subprocess.run", side_effect=_make_deb_run_side_effect(tmp_path, "pkg", "1.0")):
            result = CliRunner().invoke(app, [
                "convert", str(pkg_dir),
                "--output-dir", str(out_dir),
            ])
        assert result.exit_code == 0
        assert "Found 1 package(s)" in result.output

    def test_directory_multi_format(self, tmp_path):
        """Directory with multiple supported formats."""
        pkg_dir = tmp_path / "packages"
        pkg_dir.mkdir()
        (pkg_dir / "app.deb").write_bytes(b"fake")
        (pkg_dir / "app.tar.gz").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = _make_deb_run_side_effect(tmp_path, "pkg", "1.0")
            result = CliRunner().invoke(app, [
                "convert", str(pkg_dir),
                "--output-dir", str(out_dir),
            ])
        assert result.exit_code == 0
        assert "Found 2 package(s)" in result.output

    def test_directory_with_parallel(self, tmp_path):
        """Directory input should work with --parallel."""
        pkg_dir = tmp_path / "packages"
        pkg_dir.mkdir()
        (pkg_dir / "a.deb").write_bytes(b"fake")
        (pkg_dir / "b.deb").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("subprocess.run", side_effect=_make_deb_run_side_effect(tmp_path, "pkg", "1.0")):
            result = CliRunner().invoke(app, [
                "convert", str(pkg_dir),
                "--parallel", "2",
                "--output-dir", str(out_dir),
            ])
        assert result.exit_code == 0
        assert "Found 2 package(s)" in result.output
        assert "succeeded" in result.output

    def test_path_not_found(self, tmp_path):
        """Non-existent path should show error."""
        result = CliRunner().invoke(app, ["convert", str(tmp_path / "nope")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "no matching" in result.output.lower() or "File not found" in result.output


class TestFindPackages:
    """Unit tests for _find_packages helper."""

    def test_finds_deb_files(self, tmp_path):
        (tmp_path / "a.deb").write_bytes(b"fake")
        (tmp_path / "b.deb").write_bytes(b"fake")
        (tmp_path / "readme.txt").write_text("hello")
        result = _find_packages(tmp_path)
        assert len(result) == 2
        assert all(p.suffix == ".deb" for p in result)

    def test_sorted_order(self, tmp_path):
        (tmp_path / "z.deb").write_bytes(b"fake")
        (tmp_path / "a.deb").write_bytes(b"fake")
        (tmp_path / "m.deb").write_bytes(b"fake")
        result = _find_packages(tmp_path)
        assert result == sorted(result)

    def test_empty_directory(self, tmp_path):
        result = _find_packages(tmp_path)
        assert result == []

    def test_recursive_finds_nested(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.deb").write_bytes(b"fake")
        (sub / "b.deb").write_bytes(b"fake")
        result = _find_packages(tmp_path, recursive=True)
        assert len(result) == 2

    def test_non_recursive_ignores_subdirs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.deb").write_bytes(b"fake")
        (sub / "b.deb").write_bytes(b"fake")
        result = _find_packages(tmp_path, recursive=False)
        assert len(result) == 1

    def test_skips_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "a.deb").write_bytes(b"fake")
        result = _find_packages(tmp_path)
        assert len(result) == 1
        assert result[0].name == "a.deb"
