import mmap
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

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
    subprocess.run(
        [str(path), "--appimage-extract"],
        cwd=temp_dir, capture_output=True, text=True, timeout=30,
    )
    sf = temp_dir / "squashfs-root"
    return sf if sf.exists() else None


def _extract_unsquashfs(path: Path, temp_dir: Path) -> Path | None:
    offset = _appimage_offset(path)
    dest = temp_dir / "squashfs-root"
    cmd = ["unsquashfs", "-d", str(dest), str(path)]
    if offset > 0:
        cmd.extend(["-o", str(offset)])
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if dest.exists():
        return dest
    subprocess.run(["unsquashfs", "-d", str(dest), str(path)], capture_output=True, text=True, timeout=60)
    return dest if dest.exists() else None


def _find_elf_deps(directory: Path) -> list[str]:
    deps: list[str] = []
    for f in directory.rglob("*"):
        if f.is_file() and not f.is_symlink():
            try:
                r = subprocess.run(["file", "-b", str(f)], capture_output=True, text=True, timeout=5)
                if "ELF" in r.stdout and ("executable" in r.stdout or "shared object" in r.stdout):
                    r2 = subprocess.run(["patchelf", "--print-needed", str(f)], capture_output=True, text=True, timeout=5)
                    for lib in r2.stdout.splitlines():
                        lib = lib.strip()
                        if lib.startswith("lib") and ".so" in lib:
                            name_only = lib[3:].split(".so")[0]
                            if name_only:
                                deps.append(name_only)
            except Exception:
                pass
    return deps


def analyze_appimage(appimage_path: str) -> PackageInfo:
    path = Path(appimage_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_appimage_"))
    try:
        squashfs = _extract_fuse(path, temp_dir)
        if not squashfs:
            squashfs = _extract_unsquashfs(path, temp_dir)
        if not squashfs:
            raise ValueError("Failed to extract AppImage")

        deps = _find_elf_deps(squashfs)

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
