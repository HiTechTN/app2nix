"""Analyzer for .7z archives — extracts and inspects ELF binaries."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import find_elf, get_libs_patchelf
from app2nix.logging import logger
from app2nix.models import PackageInfo


def analyze_7z(archive_path: str) -> PackageInfo:
    """Analyze a .7z archive.

    Extracts the archive to a temporary directory, finds ELF binaries,
    and collects their shared library dependencies via patchelf.
    """
    path = Path(archive_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_7z_"))
    try:
        # Extract using 7z
        subprocess.run(
            ["7z", "x", str(path), f"-o{temp_dir}", "-y"],
            capture_output=True, check=True,
        )

        # Analyze ELF binaries
        executables = find_elf(temp_dir)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(get_libs_patchelf(exe))

        # Derive name from filename
        name = path.stem

        logger.info(
            "7z analysis complete: %s, %d ELF binaries, %d libraries",
            name, len(executables), len(all_libs),
        )

        return PackageInfo(
            name=name,
            version="1.0",
            architecture="x86_64",
            format="7z",
            dependencies=sorted(all_libs),
            executables=[str(p.relative_to(temp_dir)) for p in executables],
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
