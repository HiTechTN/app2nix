#!/usr/bin/env python3
"""
app2nix_gui.py — DEPRECATED

This file is kept for backwards compatibility.
Please use 'app2nix gui' or 'app2nix-gui' instead.
"""
import sys
import warnings

warnings.warn(
    "app2nix_gui.py is deprecated. Use 'app2nix gui' or 'app2nix-gui' instead.",
    DeprecationWarning,
    stacklevel=2,
)

try:
    from app2nix.gui import run_gui
    run_gui()
except ImportError as e:
    print(f"app2nix gui: {e}", file=sys.stderr)
    print("Install with: pip install 'app2nix[gui]'", file=sys.stderr)
    sys.exit(1)
