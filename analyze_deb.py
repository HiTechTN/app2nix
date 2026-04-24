#!/usr/bin/env python3
"""
Analyze .deb packages and extract binary dependencies using dpkg and patchelf.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

NIX_PATHS = [
    "/run/current-system/sw/bin",
    os.path.expanduser("~/.nix-profile/bin"),
    "/usr/bin",
    "/usr/local/bin",
]


def find_executable(name: str) -> str:
    """Find executable in various paths."""
    # Check each path
    for p in NIX_PATHS:
        candidate = os.path.join(p, name)
        if os.path.exists(candidate):
            # Fix permissions if needed
            if not os.access(candidate, os.X_OK):
                try:
                    subprocess.run(["chmod", "755", candidate], check=False, capture_output=True)
                except Exception:
                    pass
            return candidate
    return name


def extract_deb(deb_path: str) -> str:
    """Extract .deb to temporary directory."""
    temp_dir = tempfile.mkdtemp(prefix="app2nix_")
    dpkg_deb = find_executable("dpkg-deb")

    # Try with pkexec if permission denied
    try:
        subprocess.run(
            [dpkg_deb, "-x", deb_path, temp_dir],
            check=True,
            capture_output=True
        )
    except PermissionError:
        # Try with pkexec
        subprocess.run(
            ["pkexec", dpkg_deb, "-x", deb_path, temp_dir],
            check=True,
            capture_output=True
        )
    return temp_dir


def find_executables(directory: str) -> list[str]:
    """Find all ELF executables and shared libraries in directory."""
    executables = []
    for _root, _dirs, files in os.walk(directory):
        for f in files:
            path = os.path.join(_root, f)
            if os.path.isfile(path):
                try:
                    result = subprocess.run(
                        ["file", "-b", path],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if "ELF" in result.stdout and ("executable" in result.stdout or "shared object" in result.stdout):
                        executables.append(path)
                except (subprocess.TimeoutExpired, Exception):
                    pass
    return executables


def get_library_dependencies(binary_path: str) -> set[str]:
    """Get shared library dependencies using ldd."""
    libraries = set()
    try:
        result = subprocess.run(
            ["ldd", binary_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                lib = parts[0]
                if lib.endswith(".so"):
                    lib_name = lib.split(".so")[0]
                    if lib_name.startswith("lib"):
                        libraries.add(lib_name[3:])
    except (subprocess.TimeoutExpired, Exception):
        pass
    return libraries


def get_patchelf_dependencies(binary_path: str) -> set[str]:
    """Get dependencies using patchelf --print-needed."""
    libraries = set()
    try:
        result = subprocess.run(
            ["patchelf", "--print-needed", binary_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.splitlines():
            lib = line.strip()
            if lib.startswith("lib") and lib.endswith(".so"):
                libraries.add(lib[3:].split(".so")[0])
    except (subprocess.TimeoutExpired, Exception):
        pass
    return libraries


def get_all_dependencies(deb_path: str) -> dict[str, Any]:
    """Analyze .deb and return all dependency information."""
    temp_dir = extract_deb(deb_path)

    try:
        executables = find_executables(temp_dir)
        all_libs = set()

        for exe in executables:
            libs = get_library_dependencies(exe)
            all_libs.update(libs)
            patchelf_libs = get_patchelf_dependencies(exe)
            all_libs.update(patchelf_libs)

        result = subprocess.run(
            ["dpkg-deb", "-I", deb_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        info = {
            "name": "unknown",
            "version": "unknown",
            "architecture": "unknown",
            "dependencies": sorted(all_libs),
            "executables": executables,
            "temp_dir": temp_dir
        }

        for line in result.stdout.splitlines():
            if line.startswith("Package:"):
                info["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                info["version"] = line.split(":", 1)[1].strip()
            elif line.startswith("Architecture:"):
                info["architecture"] = line.split(":", 1)[1].strip()

        return info

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Analyze .deb packages for Nix conversion")
    parser.add_argument("deb_file", help="Path to .deb file")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    if not os.path.exists(args.deb_file):
        print(f"Error: File not found: {args.deb_file}", file=sys.stderr)
        sys.exit(1)

    info = get_all_dependencies(args.deb_file)
    output = json.dumps(info, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
