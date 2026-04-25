#!/usr/bin/env python3
"""
Utility functions for app2nix.
"""

import os
import subprocess


def verify_deb_file(path: str) -> bool:
    """Verify if file is a valid .deb package."""
    if not os.path.exists(path):
        return False
    if not path.endswith(".deb"):
        return False
    try:
        result = subprocess.run(
            ["dpkg-deb", "-I", path],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def get_deb_info(path: str) -> dict:
    """Get package info using dpkg-deb."""
    result = subprocess.run(
        ["dpkg-deb", "-I", path],
        capture_output=True,
        text=True,
        timeout=10
    )

    info = {}
    for line in result.stdout.splitlines():
        if line.startswith("Package:"):
            info["package"] = line.split(":", 1)[1].strip()
        elif line.startswith("Version:"):
            info["version"] = line.split(":", 1)[1].strip()
        elif line.startswith("Architecture:"):
            info["architecture"] = line.split(":", 1)[1].strip()
        elif line.startswith("Depends:"):
            info["depends"] = line.split(":", 1)[1].strip()
        elif line.startswith("Description:"):
            info["description"] = line.split(":", 1)[1].strip()

    return info


def extract_deb(path: str, dest: str | None = None) -> str:
    """Extract .deb to directory."""
    if dest is None:
        import tempfile
        dest = tempfile.mkdtemp(prefix="app2nix_")

    subprocess.run(
        ["dpkg-deb", "-x", path, dest],
        check=True,
        capture_output=True
    )
    return dest


def list_deb_contents(path: str) -> list[str]:
    """List contents of .deb file."""
    result = subprocess.run(
        ["dpkg-deb", "-c", path],
        capture_output=True,
        text=True,
        timeout=10
    )

    files = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 6:
            files.append(parts[-1])

    return files


def find_binaries(path: str) -> list[str]:
    """Find executable binaries in extracted .deb."""
    binaries = []

    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp) and os.access(fp, os.X_OK):
                binaries.append(fp)

    return binaries


def fix_shebang(path: str, new_interpreter: str) -> None:
    """Fix shebang in script."""
    with open(path) as f:
        first_line = f.readline()

    if first_line.startswith("#!"):
        with open(path) as f:
            content = f.read()
        content = content.replace(first_line, f"#!{new_interpreter}\n", 1)
        with open(path, "w") as f:
            f.write(content)


def patch_rpath(binary: str, new_path: str) -> bool:
    """Patch rpath in binary using patchelf."""
    try:
        subprocess.run(
            ["patchelf", "--set-rpath", new_path, binary],
            check=True,
            capture_output=True
        )
        return True
    except Exception:
        return False


def check_patchelf_available() -> bool:
    """Check if patchelf is available."""
    try:
        subprocess.run(
            ["patchelf", "--version"],
            check=True,
            capture_output=True
        )
        return True
    except Exception:
        return False


def check_dpkg_available() -> bool:
    """Check if dpkg-deb is available."""
    try:
        subprocess.run(
            ["dpkg-deb", "--version"],
            check=True,
            capture_output=True
        )
        return True
    except Exception:
        return False
