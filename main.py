#!/usr/bin/env python3
import sys
import warnings
warnings.warn(
    "main.py is deprecated. Use 'python -m app2nix convert' or 'app2nix convert' instead.",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    from app2nix.cli import app
    sys.argv[0] = "app2nix"
    if len(sys.argv) == 1:
        sys.argv.append("--help")
    app()
