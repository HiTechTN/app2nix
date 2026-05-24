#!/usr/bin/env python3
import sys
import warnings
warnings.warn(
    "server.py is deprecated. Use 'python -m app2nix serve' or 'app2nix serve' instead.",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    from app2nix.cli import app
    sys.argv = ["app2nix", "serve"] + sys.argv[1:]
    app()
