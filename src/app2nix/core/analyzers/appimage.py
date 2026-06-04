import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import find_elf, get_libs_patchelf
from app2nix.logging import logger
from app2nix.models import PackageInfo


def _validate_squashfs_superblock(data: bytes, offset: int) -> bool:
    if len(data) < offset + 20:
        return False
    inodes = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
    block_size = struct.unpack("<I", data[offset + 12 : offset + 16])[0]
    fragments = struct.unpack("<I", data[offset + 16 : offset + 20])[0]
    return 0 < inodes < 10000000 and 4096 <= block_size <= 1048576 and 0 <= fragments < 10000000


def _appimage_offset(path: Path) -> int:
    with open(path, "rb") as f:
        f.seek(-8, 2)
        data = f.read(8).decode("ascii", errors="ignore").strip()
        if data.isdigit():
            offset = int(data)
            if offset > 0:
                return offset

    elf_end = 0
    try:
        with open(path, "rb") as f:
            header = f.read(64)
            if header[:4] == b"\x7fELF":
                e_phoff = struct.unpack("<Q", header[32:40])[0]
                e_phentsize = struct.unpack("<H", header[54:56])[0]
                e_phnum = struct.unpack("<H", header[56:58])[0]
                for i in range(e_phnum):
                    ph_offset = e_phoff + i * e_phentsize
                    f.seek(ph_offset)
                    ph_data = f.read(e_phentsize)
                    if len(ph_data) < e_phentsize:
                        break
                    p_type = struct.unpack("<I", ph_data[:4])[0]
                    if p_type != 1:
                        continue
                    p_filesz = struct.unpack("<Q", ph_data[32:40])[0]
                    p_offset = struct.unpack("<Q", ph_data[8:16])[0]
                    end = p_offset + p_filesz
                    if end > elf_end:
                        elf_end = end
    except Exception:
        pass

    with open(path, "rb") as f:
        file_data = f.read()
        search_start = max(elf_end, 0)
        idx = search_start
        first_valid = -1
        while True:
            idx = file_data.find(b"hsqs", idx)
            if idx == -1:
                break
            if idx < 8:
                idx += 1
                continue
            if _validate_squashfs_superblock(file_data, idx):
                return idx
            if first_valid == -1 and idx > elf_end:
                first_valid = idx
            idx += 1
        if first_valid != -1:
            return first_valid
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
    cmd = ["unsquashfs", "-d", str(dest)]
    if offset > 0:
        cmd.extend(["-o", str(offset)])
    cmd.append(str(path))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if dest.exists():
        return dest

    logger.warning("unsquashfs with offset %s failed: %s", offset, result.stderr.strip())
    cmd2 = ["unsquashfs", "-d", str(dest), str(path)]
    subprocess.run(cmd2, capture_output=True, text=True, timeout=120)
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
                "Install squashfs-tools: nix-shell -p squashfs-tools\n"
                "On non-NixOS: sudo apt install squashfs-tools / sudo dnf install squashfs-tools"
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
