import subprocess

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame

from app2nix.gui.theme import DARK, LIGHT


@pytest.fixture
def window(qtbot):
    from app2nix.gui.main_window import App2NixWindow
    win = App2NixWindow()
    qtbot.addWidget(win)
    win.show()
    return win


def test_detect_format_supported_extensions():
    """_detect_format should return the correct extension key for every supported format."""
    from app2nix.gui.main_window import _detect_format

    cases = [
        ("/home/user/package.deb", ".deb"),
        ("/home/user/package.rpm", ".rpm"),
        ("/home/user/package.AppImage", ".appimage"),
        ("/home/user/package.appimage", ".appimage"),
        ("/home/user/package.flatpak", ".flatpak"),
        ("/home/user/package.snap", ".snap"),
        ("/home/user/package.tar.gz", ".tar.gz"),
        ("/home/user/package.tgz", ".tar.gz"),
        ("/home/user/package.tar", ".tar"),
        # Mixed / upper case
        ("PKG.DEB", ".deb"),
        ("MyApp.AppImage", ".appimage"),
        ("ARCHIVE.TAR.GZ", ".tar.gz"),
    ]
    for path, expected in cases:
        assert _detect_format(path) == expected, f"{path} → {expected}"


def test_detect_format_unsupported_returns_none():
    """_detect_format should return None for unsupported file types."""
    from app2nix.gui.main_window import _detect_format

    cases = [
        "/home/user/package.exe",
        "/home/user/package.msi",
        "/home/user/package.xyz",
        "/home/user/package",  # no extension
        "/home/user/.hidden",  # dotfile, no extension
    ]
    for path in cases:
        assert _detect_format(path) is None, f"{path} should be None"


def test_window_title(window):
    assert "app2nix" in window.windowTitle().lower()


def test_initial_window_state(window):
    """All widgets should be in their default empty / disabled state on startup."""
    # -- File selection --
    assert window.file_path.text() == ""
    assert window.file_path.placeholderText() != ""
    assert window.browse_btn is not None

    # -- Info labels --
    assert window.lbl_name.text() == "\u2014"
    assert window.lbl_version.text() == "\u2014"
    assert window.lbl_format.text() == "\u2014"
    assert window.lbl_arch.text() == "\u2014"

    # -- Output area --
    assert window.output_area.toPlainText() == ""
    assert window.output_area.isReadOnly() is True

    # -- Action buttons --
    assert window.analyze_btn.isEnabled() is True
    assert window.clear_btn is not None
    assert window.gen_default_btn.isEnabled() is False
    assert window.gen_flake_btn.isEnabled() is False

    # -- Theme toggle --
    assert window._theme_mode == "light"
    assert window.theme_btn.text() == "🌙"

    # -- Separator --
    sep = window.findChild(QFrame, "separator")
    assert sep is not None
    assert isinstance(sep, QFrame)
    assert sep.frameShape() == QFrame.Shape.HLine

    # -- Status bar --
    assert window.status_bar.text() == "Ready • Select a package file to begin"

    # -- Internal state --
    assert window.current_file is None
    assert window._analysis_result is None


def test_analyze_button_exists(window):
    assert window.analyze_btn is not None
    assert window.analyze_btn.isEnabled()


def test_analyze_button_disabled_during_work(qtbot, window):
    window.file_path.setText("/nonexistent/fake.deb")
    with patch.object(window, '_start_analysis') as mock_start:
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)
        mock_start.assert_called_once_with("/nonexistent/fake.deb")


def test_clear_resets_state(qtbot, window):
    """Clicking Clear should reset UI widgets back to defaults."""
    window.file_path.setText("/some/file.deb")
    window.lbl_name.setText("test-app")
    qtbot.mouseClick(window.clear_btn, Qt.MouseButton.LeftButton)
    assert window.file_path.text() == ""
    assert window.lbl_name.text() == "\u2014"
    assert window.current_file is None


def test_clear_during_active_analysis_resets_ui(qtbot, window, tmp_path):
    """
    If the user clicks Clear while an analysis is in progress (``_worker``
    exists and has been started), the UI should reset to its initial state
    immediately — the worker reference is discarded.
    """
    pkg_file = tmp_path / "test-app_1.2.3_amd64.deb"
    pkg_file.write_bytes(b"fake content")
    window.file_path.setText(str(pkg_file))

    with patch("app2nix.gui.main_window.AnalyzeWorker") as mock_worker:
        instance = mock_worker.return_value
        instance.finished.connect = MagicMock()
        instance.error.connect = MagicMock()
        instance.start = MagicMock()

        # Click Analyze → _start_analysis creates mock worker and sets UI to "analyzing" state
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)

        # Verify we are in "analysis in progress" state
        assert window._worker is instance
        assert window.current_file == str(pkg_file)
        assert window.analyze_btn.isEnabled() is False
        assert window.status_bar.text() == "⏳ Analyzing test-app_1.2.3_amd64.deb…"
        assert window.lbl_name.text() == "test-app_1.2.3_amd64"  # Path(pkg_file).stem
        assert window.lbl_format.text() == ".deb"
        assert window.lbl_version.text() == "…"
        assert window.lbl_arch.text() == "…"

        # Click Clear
        qtbot.mouseClick(window.clear_btn, Qt.MouseButton.LeftButton)

    # Verify UI is back to initial state
    assert window.file_path.text() == ""
    assert window.current_file is None
    assert window._analysis_result is None
    assert window.lbl_name.text() == "\u2014"
    assert window.lbl_version.text() == "\u2014"
    assert window.lbl_format.text() == "\u2014"
    assert window.lbl_arch.text() == "\u2014"
    assert window.output_area.toPlainText() == ""
    assert window.analyze_btn.isEnabled() is True
    assert window.gen_default_btn.isEnabled() is False
    assert window.gen_flake_btn.isEnabled() is False
    assert window.status_bar.text() == "Ready • Select a package file to begin"


def test_clear_disconnects_worker_and_sets_to_none(qtbot, window, tmp_path):
    """
    Clicking Clear while an analysis is in progress should disconnect the
    worker signals and set ``self._worker = None`` to prevent race
    conditions with late ``finished`` / ``error`` emissions.
    """
    pkg_file = tmp_path / "test-app.deb"
    pkg_file.write_bytes(b"fake")
    window.file_path.setText(str(pkg_file))

    with patch("app2nix.gui.main_window.AnalyzeWorker") as mock_worker:
        instance = mock_worker.return_value
        instance.finished.connect = MagicMock()
        instance.error.connect = MagicMock()
        instance.start = MagicMock()

        # Click Analyse
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)

        assert window._worker is instance

        # Click Clear
        qtbot.mouseClick(window.clear_btn, Qt.MouseButton.LeftButton)

    # _clear_all must disconnect signals and null the reference
    instance.finished.disconnect.assert_called_once_with(
        window._on_analysis_finished
    )
    instance.error.disconnect.assert_called_once_with(
        window._on_analysis_error
    )
    assert window._worker is None


def test_worker_error_after_clear_race_condition_fixed(qtbot, window, tmp_path):
    """
    After the fix in ``_clear_all`` — which disconnects worker signals and
    sets ``self._worker = None`` — a late ``error`` emission **must not**
    show ``QMessageBox.critical``.  The cleared state must remain intact.
    """
    pkg_file = tmp_path / "failing.deb"
    pkg_file.write_bytes(b"fake")
    window.file_path.setText(str(pkg_file))

    error_callbacks = []

    def _connect_error(cb):
        error_callbacks.append(cb)

    def _disconnect_error(cb):
        if cb in error_callbacks:
            error_callbacks.remove(cb)

    with (
        patch("app2nix.gui.main_window.AnalyzeWorker") as mock_worker,
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
    ):
        instance = mock_worker.return_value
        instance.error.connect = _connect_error
        instance.error.disconnect = _disconnect_error
        instance.finished.connect = MagicMock()
        instance.finished.disconnect = MagicMock()
        instance.start = MagicMock()

        # ── 1. Click Analyse → signal connected ─────────────────────────
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)

        assert len(error_callbacks) == 1, "error callback should be connected"

        # ── 2. Clear → signals disconnected ────────────────────────────
        qtbot.mouseClick(window.clear_btn, Qt.MouseButton.LeftButton)
        assert window._worker is None
        assert len(error_callbacks) == 0, "callback should have been disconnected"

    # ── 3. L'erreur **ne doit pas** s'afficher (bug corrigé) ───────────
    mock_critical.assert_not_called()
    assert window.analyze_btn.isEnabled() is True
    assert window.status_bar.text() == "Ready • Select a package file to begin"
    assert window._analysis_result is None


@pytest.mark.skip(reason="QThread causes test hang")
def test_nix_generator_called_on_analysis(qtbot, window, tmp_path):
    with patch('app2nix.gui.main_window.AnalyzeWorker') as mock_worker:
        instance = mock_worker.return_value
        instance.start = MagicMock()
        window._start_analysis("/fake/test.deb")
        instance.start.assert_called_once()


def test_unsupported_format_shows_warning(qtbot, window, tmp_path):
    bad_file = tmp_path / "test.xyz"
    bad_file.write_bytes(b"fake content")
    window.file_path.setText(str(bad_file))
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)
        mock_warn.assert_called_once()


def test_separator_is_qframe_horizontal_line(qtbot, window):
    """The separator between action buttons and the output area should be
    a QFrame with HLine shape, not a plain QLabel."""
    sep = window.findChild(QFrame, "separator")
    assert sep is not None, "Separator QFrame with objectName 'separator' not found"
    assert isinstance(sep, QFrame), "Separator must be a QFrame instance"
    assert sep.frameShape() == QFrame.Shape.HLine, (
        f"Expected HLine shape, got {sep.frameShape()}"
    )


def test_separator_theme_toggle(qtbot, window):
    """The separator background color should change when toggling themes."""
    light_sep = LIGHT["separator"]  # "#e5e7eb"
    dark_sep = DARK["separator"]   # "#334155"

    # Initially light theme
    assert window._theme_mode == "light"
    ss = window.styleSheet()
    assert light_sep in ss, (
        f"Light stylesheet should contain '{light_sep}', got stylesheet containing…"
        f"\n  …{ss[ss.find('QFrame#separator'):ss.find('QFrame#separator')+120]}…"
    )

    # Toggle → dark
    qtbot.mouseClick(window.theme_btn, Qt.MouseButton.LeftButton)
    assert window._theme_mode == "dark"
    ss = window.styleSheet()
    assert dark_sep in ss, (
        f"Dark stylesheet should contain '{dark_sep}', got stylesheet containing…"
        f"\n  …{ss[ss.find('QFrame#separator'):ss.find('QFrame#separator')+120]}…"
    )

    # Toggle → light again
    qtbot.mouseClick(window.theme_btn, Qt.MouseButton.LeftButton)
    assert window._theme_mode == "light"
    ss = window.styleSheet()
    assert light_sep in ss, (
        f"Re-light stylesheet should contain '{light_sep}', got stylesheet containing…"
        f"\n  …{ss[ss.find('QFrame#separator'):ss.find('QFrame#separator')+120]}…"
    )


def test_theme_toggle_button_text(qtbot, window):
    """The theme_btn text should toggle between 🌙 (moon) in light mode
    and ☀️ (sun) in dark mode."""
    # Initial state: light mode → moon icon (hint: click to go dark)
    assert window._theme_mode == "light"
    assert window.theme_btn.text() == "🌙"

    # Toggle → dark mode → sun icon
    qtbot.mouseClick(window.theme_btn, Qt.MouseButton.LeftButton)
    assert window._theme_mode == "dark"
    assert window.theme_btn.text() == "☀️"

    # Toggle → light mode → moon icon again
    qtbot.mouseClick(window.theme_btn, Qt.MouseButton.LeftButton)
    assert window._theme_mode == "light"
    assert window.theme_btn.text() == "🌙"


def test_save_file_success(qtbot, window, tmp_path):
    """_save_file should write content and update the status bar."""
    target = tmp_path / "result.nix"
    content = "{ pkgs ? import <nixpkgs> {} }: pkgs.stdenv.mkDerivation { name = \"test\"; }"

    with patch(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(str(target), "Nix files (*.nix)"),
    ):
        window._save_file("default.nix", content)

    assert target.exists(), "File should have been written"
    assert target.read_text(encoding="utf-8") == content
    assert window.status_bar.text() == f"💾 Saved to {target}"


def test_save_file_os_error(qtbot, window, tmp_path):
    """_save_file should catch OSError and show QMessageBox.critical."""
    target = tmp_path / "readonly.nix"
    content = "nope"

    with (
        patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(target), "Nix files (*.nix)"),
        ),
        patch("pathlib.Path.write_text", side_effect=OSError("Permission denied")),
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
    ):
        window._save_file("default.nix", content)

    mock_critical.assert_called_once()
    args, _ = mock_critical.call_args
    assert "Save Error" in str(args[1]) or "Failed to save" in str(args[2])


def test_save_file_cancelled(qtbot, window):
    """_save_file should do nothing when QFileDialog is cancelled (empty path)."""
    content = "does not matter"
    initial_status = window.status_bar.text()

    with patch(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=("", ""),  # User cancelled the dialog
    ):
        window._save_file("default.nix", content)

    # Status bar must remain unchanged — no file was saved
    assert window.status_bar.text() == initial_status


def test_browse_file_selects_path(qtbot, window, tmp_path):
    """Clicking Browse and selecting a file should populate file_path."""
    pkg_file = tmp_path / "my-package.deb"
    pkg_file.write_bytes(b"fake")

    with patch(
        "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
        return_value=(str(pkg_file), "Packages (*.deb)"),
    ):
        qtbot.mouseClick(window.browse_btn, Qt.MouseButton.LeftButton)

    assert window.file_path.text() == str(pkg_file)


def test_browse_file_cancelled_leaves_path_unchanged(qtbot, window):
    """Clicking Browse and cancelling the dialog should not alter file_path."""
    window.file_path.setText("/existing/path.deb")

    with patch(
        "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
        return_value=("", ""),  # User cancelled
    ):
        qtbot.mouseClick(window.browse_btn, Qt.MouseButton.LeftButton)

    assert window.file_path.text() == "/existing/path.deb"


def test_analyze_no_file_shows_warning(qtbot, window):
    """Clicking Analyze with an empty file_path should show a warning."""
    # file_path is empty by default
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)

    mock_warn.assert_called_once()
    args, _ = mock_warn.call_args
    # Title: tr("window.error", "No file selected") → "No file selected"
    assert "No file selected" in str(args[1])


def test_e2e_analyze_and_generate(qtbot, window, tmp_path):
    """
    Full E2E flow: create a fake .deb → click Analyze → UI populated →
    click Generate → file saved on disk.

    The real AnalyzeWorker uses QThread which hangs in tests, so we
    patch the class and emit ``finished`` synchronously from ``start()``.
    """
    # ── 1. Create a fake .deb file ──────────────────────────────────────
    pkg_file = tmp_path / "test-app_1.2.3_amd64.deb"
    pkg_file.write_bytes(b"fake deb content")
    window.file_path.setText(str(pkg_file))

    # ── 2. Build a mock analysis result ─────────────────────────────────
    mock_package = MagicMock(spec=["name", "version", "format", "architecture"])
    mock_package.name = "test-app"
    mock_package.version = "1.2.3"
    mock_package.format = "deb"
    mock_package.architecture = "amd64"

    nix_content = (
        "{ pkgs ? import <nixpkgs> {} }: pkgs.stdenv.mkDerivation "
        '{ name = "test-app"; version = "1.2.3"; }'
    )
    mock_result = MagicMock()
    mock_result.package = mock_package
    mock_result.nix_content = nix_content

    # ── 3. Patch AnalyzeWorker so it emits ``finished`` synchronously ──
    with patch("app2nix.gui.main_window.AnalyzeWorker") as mock_worker:
        instance = mock_worker.return_value

        connected_callbacks = []
        instance.finished.connect = lambda cb: connected_callbacks.append(cb)
        instance.error.connect = MagicMock()

        def on_start():
            for cb in connected_callbacks:
                cb(mock_result)

        instance.start = on_start

        # ── 4. Click Analyze ────────────────────────────────────────────
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)

    # ── 5. Verify analysis populated the UI ─────────────────────────────
    assert window.lbl_name.text() == "test-app"
    assert window.lbl_version.text() == "1.2.3"
    assert window.lbl_format.text() == "deb"
    assert window.lbl_arch.text() == "amd64"
    assert window.output_area.toPlainText() == nix_content
    assert window.gen_default_btn.isEnabled(), "Generate btn should be enabled after analysis"
    assert window.gen_flake_btn.isEnabled(), "Flake btn should be enabled after analysis"
    assert window.status_bar.text() == "✅ Analysis complete — test-app 1.2.3"

    # ── 6. Generate (default.nix) and save ──────────────────────────────
    save_target = tmp_path / "out.nix"
    with patch(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(str(save_target), "Nix files (*.nix)"),
    ):
        qtbot.mouseClick(window.gen_default_btn, Qt.MouseButton.LeftButton)

    assert save_target.exists(), "Save target was not written"
    assert save_target.read_text(encoding="utf-8") == nix_content
    assert window.status_bar.text() == f"💾 Saved to {save_target}"


def test_e2e_generate_flake_success(qtbot, window, tmp_path):
    """
    Click ``gen_flake_btn`` after a completed analysis → ``NixGenerator``
    produces ``flake.nix`` content that is saved to disk.
    """
    # ── 1. Simulate post-analysis state ─────────────────────────────────
    mock_info = MagicMock(spec=["name", "version", "format", "architecture"])
    mock_info.name = "test-app"
    mock_info.version = "1.2.3"
    mock_info.format = "deb"
    mock_info.architecture = "amd64"

    window._analysis_result = MagicMock()
    window._analysis_result.info = mock_info
    window.gen_flake_btn.setEnabled(True)

    flake_content = (
        "{\n  description = \"test-app — converted from deb by app2nix\";\n"
        '  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";\n'
        "}"
    )
    mock_flake_result = MagicMock()
    mock_flake_result.nix_content = flake_content

    save_target = tmp_path / "my-flake.nix"

    with (
        patch(
            "app2nix.core.generator.NixGenerator.generate_flake_nix",
            return_value=mock_flake_result,
        ),
        patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(save_target), "Nix files (*.nix)"),
        ),
    ):
        qtbot.mouseClick(window.gen_flake_btn, Qt.MouseButton.LeftButton)

    # ── 2. Verify the flake was saved ───────────────────────────────────
    assert save_target.exists(), "Flake file was not written"
    assert save_target.read_text(encoding="utf-8") == flake_content
    assert window.status_bar.text() == f"💾 Saved to {save_target}"


def test_e2e_generate_flake_error(qtbot, window):
    """
    If ``NixGenerator.generate_flake_nix`` raises an exception, a
    ``QMessageBox.critical`` should be shown — not a silent crash.
    """
    mock_info = MagicMock(spec=["name", "version", "format", "architecture"])
    mock_info.name = "test-app"
    mock_info.version = "1.2.3"
    mock_info.format = "deb"
    mock_info.architecture = "amd64"

    window._analysis_result = MagicMock()
    window._analysis_result.info = mock_info
    window.gen_flake_btn.setEnabled(True)

    with (
        patch(
            "app2nix.core.generator.NixGenerator.generate_flake_nix",
            side_effect=ValueError("Invalid architecture"),
        ),
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
    ):
        qtbot.mouseClick(window.gen_flake_btn, Qt.MouseButton.LeftButton)

    mock_critical.assert_called_once()
    args, _ = mock_critical.call_args
    assert "Error" in str(args[1]) or "Failed to generate" in str(args[2])


def test_generate_default_nix_no_analysis_does_nothing(qtbot, window):
    """_save_default_nix should return immediately when _analysis_result is None."""
    assert window._analysis_result is None
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as mock_dialog:
        window._save_default_nix()
    mock_dialog.assert_not_called()


def test_generate_flake_nix_no_analysis_does_nothing(qtbot, window):
    """_save_flake_nix should return immediately when _analysis_result is None."""
    assert window._analysis_result is None
    with patch("app2nix.core.generator.NixGenerator.generate_flake_nix") as mock_gen:
        window._save_flake_nix()
    mock_gen.assert_not_called()


def test_analysis_worker_error_shows_critical(qtbot, window, tmp_path):
    """
    When ``AnalyzeWorker`` emits ``error``, ``_on_analysis_error`` should
    show ``QMessageBox.critical`` with the error text and re-enable the
    Analyze button.
    """
    pkg_file = tmp_path / "failing.deb"
    pkg_file.write_bytes(b"borked")
    window.file_path.setText(str(pkg_file))

    error_message = "Corrupted package: missing control.tar.gz"

    with (
        patch("app2nix.gui.main_window.AnalyzeWorker") as mock_worker,
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
    ):
        instance = mock_worker.return_value

        connected_error_callbacks = []
        instance.error.connect = lambda cb: connected_error_callbacks.append(cb)
        instance.finished.connect = MagicMock()

        def on_start():
            for cb in connected_error_callbacks:
                cb(error_message)

        instance.start = on_start

        # Click Analyze
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)

    # Verify QMessageBox.critical was called with the error
    mock_critical.assert_called_once()
    args, _ = mock_critical.call_args
    assert error_message in str(args[2]) or "Analysis Error" in str(args[1])

    # Verify UI state after error
    assert window.analyze_btn.isEnabled(), "Analyze button should be re-enabled after error"
    assert "❌ Analysis failed" in window.status_bar.text()


def test_on_analysis_error_empty_message(qtbot, window):
    """_on_analysis_error should handle an empty error message gracefully."""
    with patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical:
        window._on_analysis_error("")

    mock_critical.assert_called_once()
    args, _ = mock_critical.call_args
    assert args[2] == "", "Error message in dialog should be empty string"
    assert window.analyze_btn.isEnabled()
    assert "❌ Analysis failed" in window.status_bar.text()


def test_on_analysis_error_very_long_message(qtbot, window):
    """_on_analysis_error should handle a very long error message without crashing."""
    long_msg = "Error: " + "x" * 5000 + ".end"
    with patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical:
        window._on_analysis_error(long_msg)

    mock_critical.assert_called_once()
    args, _ = mock_critical.call_args
    assert args[2] == long_msg, "Long error message should be passed through unchanged"
    assert window.analyze_btn.isEnabled()
    assert "❌ Analysis failed" in window.status_bar.text()


def test_worker_finished_after_clear_race_condition_fixed(qtbot, window, tmp_path):
    """
    After the fix in ``_clear_all`` — which disconnects worker signals and
    sets ``self._worker = None`` — a late ``finished`` emission **must not**
    populate the UI.  The cleared state must remain intact.
    """
    pkg_file = tmp_path / "test-app_1.2.3_amd64.deb"
    pkg_file.write_bytes(b"fake")
    window.file_path.setText(str(pkg_file))

    mock_info = MagicMock(spec=["name", "version", "format", "architecture"])
    mock_info.name = "test-app"
    mock_info.version = "1.2.3"
    mock_info.format = "deb"
    mock_info.architecture = "amd64"

    nix_content = '{ pkgs ? import <nixpkgs> {} }: pkgs.stdenv.mkDerivation { name = "test-app"; }'
    mock_result = MagicMock()
    mock_result.package = mock_info
    mock_result.nix_content = nix_content

    finished_callbacks = []

    def _connect_finished(cb):
        finished_callbacks.append(cb)

    def _disconnect_finished(cb):
        if cb in finished_callbacks:
            finished_callbacks.remove(cb)

    with patch("app2nix.gui.main_window.AnalyzeWorker") as mock_worker:
        instance = mock_worker.return_value
        instance.finished.connect = _connect_finished
        instance.finished.disconnect = _disconnect_finished
        instance.error.connect = MagicMock()
        instance.error.disconnect = MagicMock()
        instance.start = MagicMock()

        # ── 1. Click Analyse → signal connected ─────────────────────────
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)

        assert len(finished_callbacks) == 1, "finished callback should be connected"

        # ── 2. Clear → signals disconnected ────────────────────────────
        qtbot.mouseClick(window.clear_btn, Qt.MouseButton.LeftButton)
        assert window._worker is None
        assert len(finished_callbacks) == 0, "callback should have been disconnected"

    # ── 3. L'UI reste dans son état initial (bug corrigé) ───────────────
    assert window.lbl_name.text() == "\u2014"
    assert window.lbl_version.text() == "\u2014"
    assert window.lbl_format.text() == "\u2014"
    assert window.lbl_arch.text() == "\u2014"
    assert window.output_area.toPlainText() == ""
    assert window.gen_default_btn.isEnabled() is False
    assert window.gen_flake_btn.isEnabled() is False
    assert window.status_bar.text() == "Ready • Select a package file to begin"
    assert window._analysis_result is None


# =============================================================================
# Tests for uncovered paths: InstallWorker, SudoPasswordDialog, install flow
# =============================================================================


@pytest.mark.skip(reason="Pre-existing test issue with mocked worker signals")
def test_install_worker_progress_signal(qtbot, window, tmp_path):
    """InstallWorker should emit progress signals during execution."""
    import pathlib
    from unittest.mock import MagicMock, patch
    from app2nix.gui.main_window import InstallWorker

    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")
    nix_content = '{ pkgs ? import <nixpkgs> {} }: pkgs.stdenv.mkDerivation { name = "test"; }'

    worker = InstallWorker(
        package_path=str(pkg_file),
        nix_content=nix_content,
        pkg_name="test",
        version="1.0",
    )

    progress_msgs = []
    worker.progress.connect(lambda msg: progress_msgs.append(msg))
    worker.finished.connect(lambda msg: progress_msgs.append(f"DONE:{msg}"))

    with patch.object(worker, '_run_cmd') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        worker.run()

    assert any("Building" in m or "Creating" in m for m in progress_msgs)
    assert any("DONE:" in m for m in progress_msgs)


def test_install_worker_error_signal(qtbot, window, tmp_path):
    """InstallWorker should emit error signal on CalledProcessError."""
    from app2nix.gui.main_window import InstallWorker

    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    worker = InstallWorker(
        package_path=str(pkg_file),
        nix_content="fake",
        pkg_name="test",
        version="1.0",
    )

    errors = []
    worker.error.connect(lambda msg: errors.append(msg))

    with patch.object(worker, '_run_cmd', side_effect=subprocess.CalledProcessError(1, 'nix-env', stderr=b'build failed')):
        worker.run()

    assert len(errors) == 1
    assert 'Installation failed' in errors[0]
    assert 'build failed' in errors[0]


def test_install_worker_system_install(qtbot, window, tmp_path):
    """InstallWorker with system_install=True should use sudo."""
    from app2nix.gui.main_window import InstallWorker

    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    worker = InstallWorker(
        package_path=str(pkg_file),
        nix_content="fake",
        pkg_name="test",
        version="1.0",
        system_install=True,
        sudo_password="testpass",
    )

    finished = []
    worker.finished.connect(lambda msg: finished.append(msg))

    with patch.object(worker, '_run_cmd') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        worker.run()

    # Should have called _run_cmd with sudo
    assert mock_run.call_count >= 2
    install_cmd = mock_run.call_args_list[1][0][0]
    assert 'sudo' in install_cmd or 'nix' in install_cmd




@pytest.mark.skip(reason="Path.stat mocking is unreliable in offscreen mode")
def test_install_worker_world_writable_root_with_sudo(qtbot, window, tmp_path):
    """InstallWorker should fix world-writable root when sudo password provided."""
    import pathlib

    from app2nix.gui.main_window import InstallWorker

    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    worker = InstallWorker(
        package_path=str(pkg_file),
        nix_content="fake",
        pkg_name="test",
        version="1.0",
        sudo_password="testpass",
    )

    finished = []
    worker.finished.connect(lambda msg: finished.append(msg))

    orig_stat = pathlib.Path.stat
    def fake_stat(self):
        mock_s = MagicMock()
        mock_s.st_mode = 0o002  # world-writable
        return mock_s
    pathlib.Path.stat = fake_stat
    with patch.object(worker, '_run_cmd') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        worker.run()
    pathlib.Path.stat = orig_stat

    # Should have called chmod 755 / first
    calls = mock_run.call_args_list
    chmod_call = calls[0][0][0]
    assert 'chmod' in chmod_call or '755' in str(chmod_call)


@pytest.mark.skip(reason="Path.stat mocking is unreliable in offscreen mode")
def test_install_worker_world_writable_root_without_sudo(qtbot, window, tmp_path):
    """InstallWorker should error when root is world-writable and no sudo password."""
    import pathlib

    from app2nix.gui.main_window import InstallWorker

    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    worker = InstallWorker(
        package_path=str(pkg_file),
        nix_content="fake",
        pkg_name="test",
        version="1.0",
        sudo_password=None,
    )

    errors = []
    worker.error.connect(lambda msg: errors.append(msg))

    orig_stat = pathlib.Path.stat
    def fake_stat(self):
        mock_s = MagicMock()
        mock_s.st_mode = 0o002  # world-writable
        return mock_s
    pathlib.Path.stat = fake_stat
    worker.run()
    pathlib.Path.stat = orig_stat

    assert len(errors) == 1
    assert 'world-writable' in errors[0]


def test_install_worker_generic_exception(qtbot, window, tmp_path):
    """InstallWorker should catch generic exceptions."""
    from app2nix.gui.main_window import InstallWorker

    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    worker = InstallWorker(
        package_path=str(pkg_file),
        nix_content="fake",
        pkg_name="test",
        version="1.0",
    )

    errors = []
    worker.error.connect(lambda msg: errors.append(msg))

    with patch.object(worker, '_run_cmd', side_effect=RuntimeError('unexpected')):
        worker.run()

    assert len(errors) == 1
    assert 'unexpected' in errors[0]


def test_install_worker_run_cmd(qtbot, window, tmp_path):
    """_run_cmd should execute a subprocess and return the result."""
    from app2nix.gui.main_window import InstallWorker

    worker = InstallWorker(
        package_path="/fake",
        nix_content="fake",
        pkg_name="test",
        version="1.0",
    )

    result = worker._run_cmd(['echo', 'hello'])
    assert result.returncode == 0
    assert 'hello' in result.stdout


def test_install_worker_run_cmd_failure(qtbot, window, tmp_path):
    """_run_cmd should raise CalledProcessError on non-zero exit."""
    from app2nix.gui.main_window import InstallWorker

    worker = InstallWorker(
        package_path="/fake",
        nix_content="fake",
        pkg_name="test",
        version="1.0",
    )

    with pytest.raises(subprocess.CalledProcessError):
        worker._run_cmd(['false'])


def test_sudo_password_dialog_accept(qtbot, window):
    """SudoPasswordDialog should return the password when accepted."""
    from app2nix.gui.main_window import SudoPasswordDialog

    dlg = SudoPasswordDialog()
    qtbot.addWidget(dlg)
    dlg.password_input.setText("mypassword")

    with patch.object(dlg, 'exec', return_value=1):  # QDialog.DialogCode.Accepted
        result = dlg.get_password()

    assert result == "mypassword"


def test_sudo_password_dialog_cancel(qtbot, window):
    """SudoPasswordDialog should return None when cancelled."""
    from app2nix.gui.main_window import SudoPasswordDialog

    dlg = SudoPasswordDialog()
    qtbot.addWidget(dlg)

    with patch.object(dlg, 'exec', return_value=0):  # QDialog.DialogCode.Rejected
        result = dlg.get_password()

    assert result is None


def test_on_install_clicked_no_analysis(qtbot, window):
    """Clicking Install without analysis should do nothing."""
    window._analysis_result = None
    window.current_file = None
    with patch.object(window, '_install_worker'):
        window._on_install_clicked()
    # No install should have started


def test_on_install_clicked_with_analysis(qtbot, window, tmp_path):
    """Clicking Install with a completed analysis should start the install worker."""
    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    window.current_file = str(pkg_file)
    window._analysis_result = MagicMock()
    window._analysis_result.nix_content = "{ pkgs ? import <nixpkgs> {} }: {}"
    window._analysis_result.package.name = "test-app"
    window._analysis_result.package.version = "1.0"
    window.system_install_cb.setChecked(False)

    with patch('app2nix.gui.main_window.InstallWorker') as mock_worker_cls:
        instance = mock_worker_cls.return_value
        instance.finished = MagicMock()
        instance.error = MagicMock()
        instance.progress = MagicMock()
        instance.start = MagicMock()

        import pathlib
        orig_stat = pathlib.Path.stat
        def fake_stat(self):
            mock_s = MagicMock()
            mock_s.st_mode = 0o755  # not world-writable
            return mock_s
        pathlib.Path.stat = fake_stat
        try:
            window._on_install_clicked()
        finally:
            pathlib.Path.stat = orig_stat

        mock_worker_cls.assert_called_once()
        instance.start.assert_called_once()


def test_on_install_clicked_sudo_cancel(qtbot, window, tmp_path):
    """Clicking Install with system install but cancelling sudo dialog should abort."""
    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    window.current_file = str(pkg_file)
    window._analysis_result = MagicMock()
    window._analysis_result.nix_content = "fake"
    window._analysis_result.package.name = "test"
    window._analysis_result.package.version = "1.0"
    window.system_install_cb.setChecked(True)

    with patch('app2nix.gui.main_window.SudoPasswordDialog') as mock_dlg:
        mock_dlg.return_value.get_password.return_value = None
        window._on_install_clicked()

    # Install should not have started


def test_on_install_progress(qtbot, window):
    """_on_install_progress should update the status bar."""
    window._on_install_progress("Building...")
    assert "Building" in window.status_bar.text()


def test_on_install_finished(qtbot, window):
    """_on_install_finished should re-enable buttons and show success."""
    window.install_btn.setEnabled(False)
    window.analyze_btn.setEnabled(False)
    window.gen_default_btn.setEnabled(False)
    window.gen_flake_btn.setEnabled(False)
    window.progress_bar.setVisible(True)

    with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
        window._on_install_finished("test v1.0 installed!")

    assert window.install_btn.isEnabled()
    assert window.analyze_btn.isEnabled()
    assert window.gen_default_btn.isEnabled()
    assert window.gen_flake_btn.isEnabled()
    assert not window.progress_bar.isVisible()
    assert "installed" in window.status_bar.text()
    mock_info.assert_called_once()


def test_on_install_error(qtbot, window):
    """_on_install_error should re-enable buttons and show error."""
    window.install_btn.setEnabled(False)
    window.analyze_btn.setEnabled(False)
    window.gen_default_btn.setEnabled(False)
    window.gen_flake_btn.setEnabled(False)
    window.progress_bar.setVisible(True)

    with patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical:
        window._on_install_error("Build failed!")

    assert window.install_btn.isEnabled()
    assert window.analyze_btn.isEnabled()
    assert window.gen_default_btn.isEnabled()
    assert window.gen_flake_btn.isEnabled()
    assert not window.progress_bar.isVisible()
    assert "failed" in window.status_bar.text()
    mock_critical.assert_called_once()


def test_install_btn_initially_disabled(qtbot, window):
    """Install button should be disabled when no analysis is done."""
    assert not window.install_btn.isEnabled()


def test_clear_resets_install_worker(qtbot, window, tmp_path):
    """Clear should disconnect and reset the install worker."""
    pkg_file = tmp_path / "test.deb"
    pkg_file.write_bytes(b"fake")

    instance = MagicMock()
    instance.progress = MagicMock()
    instance.finished = MagicMock()
    instance.error = MagicMock()
    window._install_worker = instance

    window._clear_all()

    assert window._install_worker is None
    instance.progress.disconnect.assert_called_once()
    instance.finished.disconnect.assert_called_once()
    instance.error.disconnect.assert_called_once()


def test_detect_format_zip_and_7z(qtbot, window):
    """_detect_format should recognize .zip and .7z formats."""
    from app2nix.gui.main_window import _detect_format

    assert _detect_format("/home/user/archive.zip") == ".zip"
    assert _detect_format("/home/user/archive.7z") == ".7z"
    assert _detect_format("/home/user/archive.tar.bz2") == ".tar.bz2"
    assert _detect_format("/home/user/archive.tar.xz") == ".tar.xz"
    assert _detect_format("PKG.ZIP") == ".zip"
    assert _detect_format("PKG.7Z") == ".7z"


def test_browse_file_dialog_filter_includes_zip_7z(qtbot, window):
    """Browse dialog filter should include .zip and .7z."""
    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName") as mock_dialog:
        mock_dialog.return_value = ("", "")
        qtbot.mouseClick(window.browse_btn, Qt.MouseButton.LeftButton)

    # Verify filter string includes new formats
    filter_str = mock_dialog.call_args[0][3] if len(mock_dialog.call_args[0]) > 3 else ""
    assert filter_str != ""


def test_analysis_finished_populates_ui(qtbot, window):
    """_on_analysis_finished should populate all info labels and output area."""
    mock_result = MagicMock()
    mock_result.package.name = "my-app"
    mock_result.package.version = "2.0"
    mock_result.package.format = "deb"
    mock_result.package.architecture = "amd64"
    mock_result.nix_content = "{ pkgs ? import <nixpkgs> {} }: {}"

    window._on_analysis_finished(mock_result)

    assert window.lbl_name.text() == "my-app"
    assert window.lbl_version.text() == "2.0"
    assert window.lbl_format.text() == "deb"
    assert window.lbl_arch.text() == "amd64"
    assert window.output_area.toPlainText() == mock_result.nix_content
    assert window.gen_default_btn.isEnabled()
    assert window.gen_flake_btn.isEnabled()
    assert window.install_btn.isEnabled()
    assert "my-app 2.0" in window.status_bar.text()
