"""
Unit tests for app2nix/logging.py — setup_logging() and logger.
"""

import logging
from unittest.mock import patch

from app2nix.logging import logger, setup_logging


class TestSetupLogging:
    def test_returns_logger_instance(self):
        result = setup_logging()
        assert isinstance(result, logging.Logger)

    def test_logger_name(self):
        result = setup_logging()
        assert result.name == "app2nix"

    def test_debug_mode_passes_debug_level_to_basic_config(self):
        """Verify setup_logging(debug=True) calls basicConfig with DEBUG level."""
        with patch("app2nix.logging.logging.basicConfig") as mock_bconfig:
            setup_logging(debug=True)
        mock_bconfig.assert_called_once()
        assert mock_bconfig.call_args.kwargs.get("level") == logging.DEBUG

    def test_default_mode_passes_info_level_to_basic_config(self):
        """Verify setup_logging(debug=False) calls basicConfig with INFO level."""
        with patch("app2nix.logging.logging.basicConfig") as mock_bconfig:
            setup_logging(debug=False)
        mock_bconfig.assert_called_once()
        assert mock_bconfig.call_args.kwargs.get("level") == logging.INFO

    def test_logger_has_handlers_after_setup(self):
        """After setup_logging(), root logger should have at least one handler."""
        root = logging.getLogger()
        assert len(root.handlers) > 0


class TestModuleLevelLogger:
    def test_logger_is_module_level_instance(self):
        assert logger is not None
        assert isinstance(logger, logging.Logger)
        assert logger.name == "app2nix"
