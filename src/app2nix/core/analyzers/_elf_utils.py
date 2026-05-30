"""Shared ELF binary analysis utilities for package analyzers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def find_elf(directory: Path) -> list[Path]:
    """Find ELF executables and shared objects in *directory*."""
    elfs: list[Path] = []
    for f in directory.rglob("*"):
        if f.is_file():
            try:
                r = subprocess.run(
                    ["file", "-b", str(f)],
                    capture_output=True, text=True, timeout=5,
                )
                if "ELF" in r.stdout and (
                    "executable" in r.stdout or "shared object" in r.stdout
                ):
                    elfs.append(f)
            except Exception:
                pass
    return elfs


def get_libs_patchelf(binary_path: Path) -> set[str]:
    """Return the set of library names required by *binary_path* via patchelf."""
    libs: set[str] = set()
    try:
        r = subprocess.run(
            ["patchelf", "--print-needed", str(binary_path)],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            lib = line.strip()
            name = extract_lib_name(lib)
            if name:
                libs.add(name)
    except Exception:
        pass
    return libs


def extract_lib_name(lib_path: str) -> str | None:
    """Extract the short library name from a soname or path.

    Examples::

        >>> extract_lib_name("libssl.so.3")
        'ssl'
        >>> extract_lib_name("/usr/lib/x86_64-linux-gnu/libc.so.6")
        'c'
        >>> extract_lib_name("foo.so") is None
        True
    """
    lib = lib_path.split("/")[-1]
    if not lib.startswith("lib") or ".so" not in lib:
        return None
    name = lib[3:].split(".so")[0]
    return name or None
