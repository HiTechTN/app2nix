#!/usr/bin/env python3
import sys
import warnings
warnings.warn(
    "analyze_deb.py is deprecated. Use 'from app2nix.core.analyzers.deb import analyze_deb' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from app2nix.core.analyzers.deb import analyze_deb  # noqa: F401
from app2nix.core.analyzers.deb import analyze_deb as get_all_dependencies  # noqa: F401

if __name__ == "__main__":
    import json
    info = analyze_deb(sys.argv[1])
    print(json.dumps(info.model_dump(), indent=2))
