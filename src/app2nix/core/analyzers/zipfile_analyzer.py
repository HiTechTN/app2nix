"""Analyzer for .zip archives — extracts and inspects ELF binaries."""

import shutil
import tempfile
import zipfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import find_elf, get_libs_patchelf
from app2nix.logging import logger
from app2nix.models import PackageInfo


def analyze_zip(zip_path: str) -> PackageInfo:
    """Analyze a .zip archive.

    Extracts the archive to a temporary directory, finds ELF binaries,
    and collects their shared library dependencies via patchelf.
    """
    path = Path(zip_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_zip_"))
    try:
        # Extract
        with zipfile.ZipFile(str(path), "r") as zf:
            zf.extractall(str(temp_dir))

        # Analyze ELF binaries
        executables = find_elf(temp_dir)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(get_libs_patchelf(exe))

        # Derive name from filename
        name = path.stem  # e.g. "myapp-1.0" from "myapp-1.0.zip"

        logger.info(
            "ZIP analysis complete: %s, %d ELF binaries, %d libraries",
            name, len(executables), len(all_libs),
        )

        return PackageInfo(
            name=name,
            version="1.0",
            architecture="x86_64",
            format="zip",
            dependencies=sorted(all_libs),
            executables=[str(p.relative_to(temp_dir)) for p in executables],
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
