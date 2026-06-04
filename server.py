"""Deprecated: use ``app2nix serve`` or ``python -m app2nix serve`` instead."""

if __name__ == "__main__":
    import sys
    import warnings

    warnings.warn(
        "server.py is deprecated. Use 'app2nix serve' or 'python -m app2nix serve' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from app2nix.cli import app as typer_app

    sys.argv = ["app2nix", "serve"] + sys.argv[1:]
    typer_app()
