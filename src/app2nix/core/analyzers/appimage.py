import mmap
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import find_elf, get_libs_patchelf
from app2nix.logging import logger
from app2nix.models import PackageInfo


def _appimage_offset(path: Path) -> int:
    with open(path, "rb") as f:
        f.seek(-8, 2)
        data = f.read(8).decode("ascii", errors="ignore").strip()
        if data.isdigit():
            offset = int(data)
            if offset > 0:
                return offset
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        idx = mm.find(b"hsqs")
        mm.close()
        if idx != -1 and idx > 0:
            return idx
    return 0


def _extract_fuse(path: Path, temp_dir: Path) -> Path | None:
    if not os.access(path, os.X_OK):
        os.chmod(path, 0o755)
    result = subprocess.run(
        [str(path), "--appimage-extract"],
        cwd=temp_dir, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.warning("FUSE extraction failed: %s", result.stderr.strip())
    sf = temp_dir / "squashfs-root"
    return sf if sf.exists() else None


def _extract_unsquashfs(path: Path, temp_dir: Path) -> Path | None:
    if not shutil.which("unsquashfs"):
        logger.error("unsquashfs not found — install squashfs-tools")
        return None
    dest = temp_dir / "squashfs-root"
    if dest.exists():
        shutil.rmtree(dest)

    offset = _appimage_offset(path)
    cmd = ["unsquashfs", "-d", str(dest), str(path)]
    if offset > 0:
        cmd.extend(["-o", str(offset)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if dest.exists():
        return dest

    logger.warning("unsquashfs with offset %s failed: %s", offset, result.stderr.strip())
    subprocess.run(["unsquashfs", "-d", str(dest), str(path)], capture_output=True, text=True, timeout=60)
    return dest if dest.exists() else None



def analyze_appimage(appimage_path: str) -> PackageInfo:
    path = Path(appimage_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_appimage_"))
    try:
        if not shutil.which("unsquashfs"):
            raise ValueError(
                "unsquashfs (squashfs-tools) is required to extract AppImages. "
                "Install it with: nix-shell -p squashfs-tools"
            )

        squashfs = _extract_fuse(path, temp_dir)
        if not squashfs:
            squashfs = _extract_unsquashfs(path, temp_dir)
        if not squashfs:
            raise ValueError(
                "Failed to extract AppImage. Tried --appimage-extract and unsquashfs. "
                "Ensure squashfs-tools is installed or the AppImage supports FUSE extraction."
            )

        executables_elf = find_elf(squashfs)
        deps: list[str] = []
        for elf in executables_elf:
            deps.extend(get_libs_patchelf(elf))

        executables = []
        for f in squashfs.rglob("*"):
            if f.is_file() and os.access(f, os.X_OK):
                executables.append(str(f.relative_to(squashfs)))

        return PackageInfo(
            name=path.stem,
            version="1.0",
            architecture="x86_64",
            format="appimage",
            dependencies=sorted(set(deps)),
            executables=executables,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
