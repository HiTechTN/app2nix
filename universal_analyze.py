#!/usr/bin/env python3
import sys
import warnings
warnings.warn(
    "universal_analyze.py is deprecated. Use 'from app2nix.core.analyzer import UniversalAnalyzer' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from app2nix.core.analyzer import UniversalAnalyzer  # noqa: F401

if __name__ == "__main__":
    import json
    analyzer = UniversalAnalyzer()
    info = analyzer.analyze(sys.argv[1])
    print(json.dumps(info.model_dump(), indent=2))
