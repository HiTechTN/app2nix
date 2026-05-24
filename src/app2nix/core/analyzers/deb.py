import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.models import PackageInfo


def analyze_deb(deb_path: str) -> PackageInfo:
    path = Path(deb_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_deb_"))
    try:
        subprocess.run(["dpkg-deb", "-x", str(path), str(temp_dir)], check=True, capture_output=True)

        name, version, arch = "unknown", "1.0", "amd64"
        deps: list[str] = []

        info_result = subprocess.run(["dpkg-deb", "-I", str(path)], capture_output=True, text=True)
        for line in info_result.stdout.splitlines():
            ls = line.strip()
            if ls.startswith("Package:"):
                name = ls.split(":", 1)[1].strip()
            elif ls.startswith("Version:"):
                version = ls.split(":", 1)[1].strip()
            elif ls.startswith("Architecture:"):
                arch = ls.split(":", 1)[1].strip()
            elif ls.startswith("Depends:"):
                deps_raw = ls.split(":", 1)[1].strip()
                for dep in deps_raw.split(","):
                    dep = dep.strip().split(" ")[0].split("|")[0].strip()
                    if dep:
                        deps.append(dep)

        executables = _find_elf(temp_dir)
        all_libs: set[str] = set()
        for exe in executables:
            all_libs.update(_get_libs_ldd(exe))
            all_libs.update(_get_libs_patchelf(exe))

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


def _get_libs_ldd(binary_path: Path) -> set[str]:
    libs: set[str] = set()
    try:
        r = subprocess.run(["ldd", str(binary_path)], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                lib = parts[0]
                name = _extract_lib_name(lib)
                if name:
                    libs.add(name)
    except Exception:
        pass
    return libs


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
