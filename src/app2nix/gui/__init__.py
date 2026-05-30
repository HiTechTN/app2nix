"""app2nix GUI — PyQt6 graphical interface."""

from app2nix.gui.main_window import App2NixWindow


def run_gui() -> None:
    """Launch the main window (blocking)."""
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    win = App2NixWindow()
    win.show()
    sys.exit(app.exec())
