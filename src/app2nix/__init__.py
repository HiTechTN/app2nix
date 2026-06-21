import os
from pathlib import Path

from app2nix.core.analyzer import UniversalAnalyzer
from app2nix.core.generator import NixGenerator


def _ensure_runtime_path() -> None:
    candidates = [
        Path(os.environ.get("SUDO_HOME", Path.home())) / ".nix-profile" / "bin",
        Path.home() / ".nix-profile" / "bin",
        Path("/run/current-system/sw/bin"),
        Path("/nix/var/nix/profiles/default/bin"),
        Path("/etc/profiles/per-user") / Path.home().name / "bin",
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
    ]
    path_dirs = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    prepend = [str(p) for p in candidates if p.exists() and p not in path_dirs]
    if prepend:
        os.environ["PATH"] = os.pathsep.join([*prepend, os.environ.get("PATH", "")])


_ensure_runtime_path()

__version__ = "3.0.1"
__all__ = ["UniversalAnalyzer", "NixGenerator"]
