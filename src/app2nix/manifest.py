"""Standalone manifest tracking and orphan cleanup for .desktop/icon files.

This module has **no** PyQt6 dependency so it can be used from the CLI,
the GUI, or any other context.

The manifest lives at ``~/.local/share/app2nix/manifest.json`` and maps
each installed package name to the desktop files, icons, and nix profile
element key recorded at install time.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------

def manifest_path() -> Path:
    """Path to the manifest file that tracks installed desktop entries and icons."""
    return Path.home() / ".local" / "share" / "app2nix" / "manifest.json"


def load_manifest() -> dict:
    """Load the install manifest from disk."""
    p = manifest_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"packages": {}}


def save_manifest(data: dict) -> None:
    """Save the install manifest to disk."""
    p = manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_install(
    pkg_name: str,
    desktop_files: list[str],
    icon_files: list[str],
    nix_profile_key: str = "",
) -> None:
    """Record installed desktop files and icons in the manifest."""
    data = load_manifest()
    safe_name = pkg_name.lower().replace(" ", "-")
    entry: dict[str, object] = {
        "desktop_files": desktop_files,
        "icon_files": icon_files,
    }
    if nix_profile_key:
        entry["nix_profile_key"] = nix_profile_key
    data["packages"][safe_name] = entry
    save_manifest(data)


# ---------------------------------------------------------------------------
# Orphan cleanup
# ---------------------------------------------------------------------------

def cleanup_orphaned_entries() -> int:
    """Remove .desktop files and icons for packages no longer in the Nix profile.

    Returns the number of packages cleaned up.
    """
    data = load_manifest()
    tracked = data.get("packages", {})
    if not tracked:
        return 0

    # Build set of currently installed package names
    installed: set[str] = set()

    # Try nix profile list --json first
    try:
        result = subprocess.run(
            ["nix", "profile", "list", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            profile = json.loads(result.stdout)
            for key, entry in profile.get("elements", {}).items():
                installed.add(key.lower())
                # Extract package name from attrPath (e.g. "nixpkgs#firefox")
                if isinstance(entry, dict):
                    attr_path = entry.get("attrPath", "")
                    if "#" in attr_path:
                        pkg = attr_path.rsplit("#", 1)[-1]
                        installed.add(pkg.lower())
                        if "-" in pkg:
                            installed.add(pkg.split("-", 1)[0].lower())
                    # Also extract from storePaths
                    for sp in entry.get("storePaths", []):
                        sp_name = Path(sp).name  # e.g. "abc123-firefox-128.0"
                        parts = sp_name.split("-", 1)
                        if len(parts) == 2:
                            installed.add(parts[1].lower())
                            if "-" in parts[1]:
                                installed.add(parts[1].split("-", 1)[0].lower())
    except Exception:
        pass

    # Fallback: nix-env -q
    try:
        result = subprocess.run(
            ["nix-env", "-q"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                name = line.strip().split("-")[0]
                if name:
                    installed.add(name.lower())
    except Exception:
        pass

    desktop_dir = Path.home() / ".local" / "share" / "applications"
    icons_dir = Path.home() / ".local" / "share" / "icons"
    cleaned = 0
    remaining: dict[str, dict] = {}

    for pkg_name, info in tracked.items():
        # Prefer exact match against stored nix profile key (case-insensitive)
        profile_key = info.get("nix_profile_key", "")
        if profile_key:
            # Check full key or just the package part after #
            if profile_key.lower() in installed:
                remaining[pkg_name] = info
                continue
            pkg_part = profile_key.rsplit("#", 1)[-1]
            if pkg_part.lower() in installed:
                remaining[pkg_name] = info
                continue
        # Fuzzy fallback for legacy manifests without stored key
        pkg_base = pkg_name.split("-")[0]
        is_installed = (
            pkg_name in installed
            or pkg_base in installed
            or any(inst in pkg_name for inst in installed)
        )
        if is_installed:
            remaining[pkg_name] = info
            continue

        # Package not in profile — remove its desktop files
        for df_rel in info.get("desktop_files", []):
            df_path = desktop_dir / df_rel
            if df_path.exists():
                df_path.unlink()

        # Remove icons
        for icon_name in info.get("icon_files", []):
            for size_dir in [
                "scalable", "16x16", "32x32", "48x48",
                "64x64", "128x128", "256x256",
            ]:
                for ext in [".png", ".svg", ".xpm", ".ico"]:
                    icon_path = icons_dir / "hicolor" / size_dir / "apps" / f"{icon_name}{ext}"
                    if icon_path.exists():
                        icon_path.unlink()
            # Legacy glob-pattern entries from older manifests
            if ".*" in icon_name:
                base = icon_name.replace(".*", "")
                for size_dir in [
                    "scalable", "16x16", "32x32", "48x48",
                    "64x64", "128x128", "256x256",
                ]:
                    apps_dir = icons_dir / "hicolor" / size_dir / "apps"
                    if apps_dir.is_dir():
                        for f in apps_dir.glob(f"{base}.*"):
                            f.unlink()

        cleaned += 1

    if cleaned > 0:
        # Refresh desktop database
        try:
            subprocess.run(
                ["update-desktop-database", str(desktop_dir)],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
        # Refresh icon cache
        try:
            subprocess.run(
                ["gtk-update-icon-cache", "-f", "-t",
                 str(icons_dir / "hicolor")],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    data["packages"] = remaining
    save_manifest(data)
    return cleaned
