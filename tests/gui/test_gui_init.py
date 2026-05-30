from unittest.mock import MagicMock, patch

from app2nix.gui import run_gui


class TestRunGui:
    @patch("app2nix.gui.sys.exit")
    @patch("app2nix.gui.App2NixWindow")
    @patch("app2nix.gui.QApplication")
    def test_run_gui_creates_app_and_shows_window(self, mock_qapp_cls, mock_window_cls, mock_exit):
        """run_gui should create QApplication, show window, and exit."""
        mock_app = MagicMock()
        mock_app.exec.return_value = 0
        mock_qapp_cls.return_value = mock_app

        mock_win = MagicMock()
        mock_window_cls.return_value = mock_win

        run_gui()

        mock_qapp_cls.assert_called_once()
        mock_window_cls.assert_called_once()
        mock_win.show.assert_called_once()
        mock_exit.assert_called_once_with(0)
