#!/usr/bin/env python3
"""server.py — DEPRECATED

Use 'app2nix serve' or 'python -m app2nix serve' instead.
"""
import sys
import warnings

warnings.warn(
    "server.py is deprecated. Use 'python -m app2nix serve' or 'app2nix serve' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from app2nix.cli import app as typer_app
sys.argv = ["app2nix", "serve"] + sys.argv[1:]
typer_app()
