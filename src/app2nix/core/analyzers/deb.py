import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import extract_lib_name, find_elf, get_libs_patchelf
from app2nix.models import PackageInfo


def analyze_deb(deb_path: str) -> PackageInfo:
    path = Path(deb_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_deb_"))

    try:
        subprocess.run(
            ["dpkg-deb", "-x", str(path), str(temp_dir)],
            check=True, capture_output=True, timeout=60,
        )

        name, version, arch = _parse_control(path)

        executables = find_elf(temp_dir)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(_get_libs_ldd(exe))
            all_libs.update(get_libs_patchelf(exe))

        return PackageInfo(
            name=name,
            version=version,
            architecture=arch,
            format="deb",
            dependencies=sorted(all_libs),
            executables=[str(p.relative_to(temp_dir)) for p in executables],
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _parse_control(deb_path: Path) -> tuple[str, str, str]:
    """Extract package name, version, and architecture from a .deb control file."""
    try:
        r = subprocess.run(
            ["dpkg-deb", "-I", str(deb_path)],
            capture_output=True, text=True, timeout=10,
        )
        name = "unknown"
        version = "1.0"
        arch = "amd64"
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("Package:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
            elif line.startswith("Architecture:"):
                arch = line.split(":", 1)[1].strip()
        return name, version, arch
    except Exception:
        return "unknown", "unknown", "unknown"


def _get_libs_ldd(binary_path: Path) -> set[str]:
    """Get shared library names needed by a binary using ldd."""
    libs: set[str] = set()
    try:
        r = subprocess.run(
            ["ldd", str(binary_path)],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = extract_lib_name(parts[0])
                if name:
                    libs.add(name)
    except Exception:
        pass
    return libs
