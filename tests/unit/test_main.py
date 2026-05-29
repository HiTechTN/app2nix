"""Tests for __main__.py — the ``python -m app2nix`` entry point."""
from pathlib import Path
from unittest.mock import patch


def test_main_calls_app():
    """``__main__.py`` should import ``app`` from ``app2nix.cli`` and call it."""
    main_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "app2nix"
        / "__main__.py"
    )
    assert main_path.exists(), f"{main_path} not found"

    with patch("app2nix.cli.app") as mock_app:
        import runpy

        runpy.run_path(str(main_path), run_name="__main__")

        mock_app.assert_called_once()
