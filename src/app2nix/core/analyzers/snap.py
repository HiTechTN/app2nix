import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.models import PackageInfo


def analyze_snap(snap_path: str) -> PackageInfo:
    path = Path(snap_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_snap_"))
    name = path.stem
    version = "1.0"
    arch = "x86_64"

    try:
        # Snap packages are squashfs images
        try:
            subprocess.run(
                ["unsquashfs", "-f", "-d", str(temp_dir / "squashfs-root"), str(path)],
                check=True, capture_output=True, timeout=60,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try with offset detection for embedded squashfs
            offset = _find_squashfs_offset(path)
            if offset > 0:
                subprocess.run(
                    ["unsquashfs", "-f", "-d", str(temp_dir / "squashfs-root"),
                     "-o", str(offset), str(path)],
                    check=True, capture_output=True, timeout=60,
                )
            else:
                return PackageInfo(
                    name=name, version=version, architecture=arch,
                    format="snap", dependencies=[], executables=[],
                )

        squashfs = temp_dir / "squashfs-root"

        # Parse snap metadata
        name, version = _parse_snap_yaml(squashfs, name, version)

        # Find ELF binaries and discover dependencies
        executables = _find_elf(squashfs)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(_get_libs_patchelf(exe))

        return PackageInfo(
            name=name,
            version=version,
            architecture=arch,
            format="snap",
            dependencies=sorted(all_libs),
            executables=[str(p.relative_to(squashfs)) for p in executables],
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _find_squashfs_offset(path: Path) -> int:
    """Find the squashfs magic bytes offset in a snap file."""
    try:
        with open(path, "rb") as f:
            content = f.read()
            # hsqs magic for squashfs
            offset = content.find(b"hsqs")
            if offset >= 0:
                return offset
    except Exception:
        pass
    return 0


def _parse_snap_yaml(squashfs: Path, default_name: str, default_version: str) -> tuple[str, str]:
    """Parse meta/snap.yaml for snap name and version."""
    snap_yaml = squashfs / "meta" / "snap.yaml"
    if not snap_yaml.exists():
        return default_name, default_version

    try:
        content = snap_yaml.read_text()
        # Simple YAML-like parsing for the fields we need
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("name:"):
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
