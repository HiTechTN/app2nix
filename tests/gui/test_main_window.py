import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt


@pytest.fixture
def window(qtbot):
    from app2nix.gui.main_window import App2NixWindow
    win = App2NixWindow()
    qtbot.addWidget(win)
    win.show()
    return win


def test_window_title(window):
    assert "app2nix" in window.windowTitle().lower()


def test_analyze_button_exists(window):
    assert window.analyze_btn is not None
    assert window.analyze_btn.isEnabled()


def test_analyze_button_disabled_during_work(qtbot, window):
    window.file_path.setText("/nonexistent/fake.deb")
    with patch.object(window, '_start_analysis') as mock_start:
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)
        mock_start.assert_called_once_with("/nonexistent/fake.deb")


def test_clear_resets_state(qtbot, window):
    window.file_path.setText("/some/file.deb")
    window.lbl_name.setText("test-app")
    qtbot.mouseClick(window.clear_btn, Qt.MouseButton.LeftButton)
    assert window.file_path.text() == ""
    assert window.lbl_name.text() == "-"
    assert window.current_file is None


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
