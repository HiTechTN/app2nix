import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import find_elf, get_libs_patchelf
from app2nix.models import PackageInfo


def analyze_tarball(tarball_path: str) -> PackageInfo:
    path = Path(tarball_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_tar_"))
    try:
        subprocess.run(["tar", "-xf", str(path), "-C", str(temp_dir)], capture_output=True)

        executables = find_elf(temp_dir)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(get_libs_patchelf(exe))

        return PackageInfo(
            name=path.stem.replace(".tar.gz", "").replace(".tgz", "").replace(".tar", ""),
            version="1.0",
            architecture="x86_64",
            format="tarball",
            dependencies=sorted(all_libs),
            executables=[str(p.relative_to(temp_dir)) for p in executables],
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
