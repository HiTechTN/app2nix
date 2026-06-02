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
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from app2nix.cli import app

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
        assert "File not found" in result.output


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
