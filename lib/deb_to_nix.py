#!/usr/bin/env python3
import warnings
warnings.warn(
    "lib/deb_to_nix.py is deprecated. Use 'from app2nix.core.resolver import DEP_MAP' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from app2nix.core.resolver import DEP_MAP as DEB_TO_NIX  # noqa: F401
from app2nix.core.resolver import DEP_MAP

def translate(lib_name: str) -> str | None:
    lib_base = lib_name.split(".so")[0]
    if lib_base.startswith("lib"):
        lib_base = lib_base[3:]
    return DEP_MAP.get(lib_base)

def translate_all(lib_names: list) -> list:
    result = set()
    for lib in lib_names:
        if lib:
            nix_pkg = translate(lib)
            if nix_pkg:
                result.add(nix_pkg)
    return sorted(result)
