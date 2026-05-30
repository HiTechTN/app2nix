import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.models import PackageInfo


def analyze_flatpak(flatpak_path: str) -> PackageInfo:
    path = Path(flatpak_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_flatpak_"))
    name = path.stem
    version = "1.0"
    arch = "x86_64"
    deps: list[str] = []

    try:
        # Flatpak bundles are squashfs images or OCI archives
        # Try extracting with unsquashfs first (squashfs-based)
        extracted = False
        try:
            subprocess.run(
                ["unsquashfs", "-f", "-d", str(temp_dir / "squashfs-root"), str(path)],
                check=True, capture_output=True, timeout=60,
            )
            extracted = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        if not extracted:
            # Try as a zip/tar archive
            try:
                subprocess.run(
                    ["tar", "xf", str(path), "-C", str(temp_dir)],
                    check=True, capture_output=True, timeout=60,
                )
                extracted = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        if not extracted:
            try:
                subprocess.run(
                    ["unzip", "-o", str(path), "-d", str(temp_dir)],
                    check=True, capture_output=True, timeout=60,
                )
                extracted = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        # Parse metadata from the extracted flatpak
        _parse_metadata(temp_dir)

        # Try to read the flatpak manifest (JSON or YAML) if present
        manifest = _find_manifest(path.parent)
        if manifest:
            name, version = _parse_manifest(manifest, name, version)

        # Find ELF binaries and discover dependencies
        executables = _find_elf(temp_dir)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(_get_libs_patchelf(exe))

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


def _parse_metadata(temp_dir: Path) -> tuple[str, str] | None:
    """Parse flatpak metadata file for app name and runtime info."""
    for candidate in [temp_dir / "metadata", temp_dir / "squashfs-root" / "metadata"]:
        if candidate.exists():
            try:
                content = candidate.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("name="):
                        return None  # Just parsing for now
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
        import json
        try:
            data = json.loads(content)
            name = data.get("id", data.get("app-id", default_name))
            version = data.get("version", default_version)
            return name, version
        except json.JSONDecodeError:
            # Try YAML-like parsing (simple key=value)
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("app-id:") or line.startswith("id:"):
                    default_name = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("version:"):
                    default_version = line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default_name, default_version


def _find_elf(directory: Path) -> list[Path]:
    elfs = []
    for f in directory.rglob("*"):
        if f.is_file():
            try:
                r = subprocess.run(["file", "-b", str(f)], capture_output=True, text=True, timeout=5)
                if "ELF" in r.stdout and ("executable" in r.stdout or "shared object" in r.stdout):
                    elfs.append(f)
            except Exception:
                pass
    return elfs


def _get_libs_patchelf(binary_path: Path) -> set[str]:
    libs: set[str] = set()
    try:
        r = subprocess.run(["patchelf", "--print-needed", str(binary_path)], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            lib = line.strip()
            name = _extract_lib_name(lib)
            if name:
                libs.add(name)
    except Exception:
        pass
    return libs


def _extract_lib_name(lib_path: str) -> str | None:
    lib = lib_path.split("/")[-1]
    if not lib.startswith("lib") or ".so" not in lib:
        return None
    name = lib[3:].split(".so")[0]
    return name if name else None
