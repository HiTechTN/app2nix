import json
import subprocess
from pathlib import Path

from app2nix.models import PackageInfo


def analyze_flatpak(flatpak_path: str) -> PackageInfo:
    path = Path(flatpak_path)
    info = PackageInfo(
        name=path.stem,
        version="1.0",
        architecture="x86_64",
        format="flatpak",
        dependencies=[],
        executables=[],
    )

    try:
        result = subprocess.run(
            ["flatpak-builder", "--show-manifest", str(path)],
            capture_output=True, text=True,
        )
        data = json.loads(result.stdout)
        info.name = data.get("id", info.name)
    except Exception:
        pass

    return info
