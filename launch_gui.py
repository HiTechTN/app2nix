#!/usr/bin/env python3
"""Launcher for app2nix GUI on NixOS — adds source to path before importing."""
import sys
from pathlib import Path

src = Path(__file__).resolve().parent / "src"
if src.is_dir():
    sys.path.insert(0, str(src))

from app2nix.gui import run_gui

run_gui()
