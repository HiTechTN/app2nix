import shutil
import subprocess
import tempfile
from pathlib import Path

from app2nix.models import PackageInfo


def analyze_tarball(tarball_path: str) -> PackageInfo:
    path = Path(tarball_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="app2nix_tar_"))
    try:
        subprocess.run(["tar", "-xf", str(path), "-C", str(temp_dir)], capture_output=True)

        deps: list[str] = []
        executables: list[str] = []
        for f in temp_dir.rglob("*"):
            if f.is_file():
                try:
                    r = subprocess.run(["file", "-b", str(f)], capture_output=True, text=True, timeout=5)
                    if "ELF" in r.stdout and ("executable" in r.stdout or "shared object" in r.stdout):
                        executables.append(str(f.relative_to(temp_dir)))
                        r2 = subprocess.run(["patchelf", "--print-needed", str(f)], capture_output=True, text=True, timeout=5)
                        for lib in r2.stdout.splitlines():
                            lib = lib.strip()
                            if lib.startswith("lib") and ".so" in lib:
                                name_only = lib[3:].split(".so")[0]
                                if name_only:
                                    deps.append(name_only)
                except Exception:
                    pass

        return PackageInfo(
            name=path.stem.replace(".tar.gz", "").replace(".tgz", "").replace(".tar", ""),
            version="1.0",
            architecture="x86_64",
            format="tarball",
            dependencies=sorted(set(deps)),
            executables=executables,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
