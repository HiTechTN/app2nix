import subprocess
from pathlib import Path

from app2nix.models import PackageInfo


def analyze_snap(snap_path: str) -> PackageInfo:
    path = Path(snap_path)
    info = PackageInfo(
        name=path.stem,
        version="1.0",
        architecture="x86_64",
        format="snap",
        dependencies=[],
        executables=[],
    )

    try:
        subprocess.run(["unsquashfs", "-l", str(path)], capture_output=True, text=True)
    except Exception:
        pass

    return info
