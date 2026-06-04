import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import find_elf, get_libs_patchelf
from app2nix.models import PackageInfo


def analyze_flatpak(flatpak_path: str) -> PackageInfo:
    path = Path(flatpak_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_flatpak_"))
    name = path.stem
    version = "1.0"
    arch = "x86_64"

    try:
        try:
            subprocess.run(
                ["unsquashfs", "-f", "-d", str(temp_dir / "squashfs-root"), str(path)],
                check=True, capture_output=True, timeout=60,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        meta_name = _parse_metadata(temp_dir)
        if meta_name:
            name = meta_name

        manifest = _find_manifest(path.parent)
        if manifest:
            name, version = _parse_manifest(manifest, name, version)

        executables = find_elf(temp_dir)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(get_libs_patchelf(exe))

        return PackageInfo(
            name=name,
            version=version,
            architecture=arch,
            format="flatpak",
            dependencies=sorted(all_libs),
            executables=[str(p.relative_to(temp_dir)) for p in executables],
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _parse_metadata(temp_dir: Path) -> str | None:
    """Parse flatpak metadata file for app name and runtime info."""
    for candidate in [temp_dir / "metadata", temp_dir / "squashfs-root" / "metadata"]:
        if candidate.exists():
            try:
                content = candidate.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("name="):
                        return line.split("=", 1)[1].strip()
            except Exception:
                pass
    return None


def _find_manifest(search_dir: Path) -> Path | None:
    """Look for a flatpak manifest (JSON or YAML) near the .flatpak file."""
    for ext in ["*.json", "*.yml", "*.yaml"]:
        for f in search_dir.glob(ext):
            try:
                content = f.read_text()
                if "app-id" in content or "id" in content:
                    return f
            except Exception:
                continue
    return None


def _parse_manifest(manifest_path: Path, default_name: str, default_version: str) -> tuple[str, str]:
    """Parse a flatpak manifest for app ID and version."""
    try:
        content = manifest_path.read_text()
        try:
            data = json.loads(content)
            name = data.get("id", data.get("app-id", default_name))
            version = data.get("version", default_version)
            return name, version
        except json.JSONDecodeError:
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("app-id:") or line.startswith("id:"):
                    default_name = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("version:"):
                    default_version = line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default_name, default_version
