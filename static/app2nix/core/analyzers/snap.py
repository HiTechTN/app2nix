import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import find_elf, get_libs_patchelf
from app2nix.models import PackageInfo


def analyze_snap(snap_path: str) -> PackageInfo:
    path = Path(snap_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_snap_"))
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

        name, version = _parse_snap_yaml(squashfs, name, version)

        executables = find_elf(squashfs)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(get_libs_patchelf(exe))

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
    """Find the offset of a squashfs image embedded in a snap file."""
    data = path.read_bytes()
    magic = b"hsqs"
    offset = data.find(magic)
    return offset if offset >= 0 else 0


def _parse_snap_yaml(squashfs: Path, default_name: str, default_version: str) -> tuple[str, str]:
    """Parse meta/snap.yaml from the extracted snap."""
    yaml_path = squashfs / "meta" / "snap.yaml"
    if not yaml_path.exists():
        return default_name, default_version
    try:
        content = yaml_path.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("name:"):
                default_name = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("version:"):
                default_version = line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default_name, default_version
