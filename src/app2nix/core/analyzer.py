from pathlib import Path

from app2nix.core.analyzers.appimage import analyze_appimage
from app2nix.core.analyzers.deb import analyze_deb
from app2nix.core.analyzers.flatpak import analyze_flatpak
from app2nix.core.analyzers.rpm import analyze_rpm
from app2nix.core.analyzers.snap import analyze_snap
from app2nix.core.analyzers.tarball import analyze_tarball
from app2nix.exceptions import UnsupportedFormatError
from app2nix.models import PackageInfo

SUPPORTED_FORMATS = {
    ".deb": ("deb", analyze_deb),
    ".rpm": ("rpm", analyze_rpm),
    ".appimage": ("appimage", analyze_appimage),
    ".flatpak": ("flatpak", analyze_flatpak),
    ".snap": ("snap", analyze_snap),
    ".tar.gz": ("tarball", analyze_tarball),
    ".tgz": ("tarball", analyze_tarball),
    ".tar": ("tarball", analyze_tarball),
}


class UniversalAnalyzer:
    def __init__(self):
        self._format_map = SUPPORTED_FORMATS

    def detect_format(self, filename: str) -> str | None:
        name = filename.lower()
        if name.endswith(".tar.gz") or name.endswith(".tgz"):
            return ".tar.gz"
        ext = Path(name).suffix
        return ext if ext in self._format_map else None

    def analyze(self, package_path: str) -> PackageInfo:
        path = Path(package_path)
        if not path.exists():
            raise FileNotFoundError(f"Package not found: {package_path}")

        fmt = self.detect_format(path.name)
        if not fmt:
            raise UnsupportedFormatError(f"Unsupported format: {path.suffix}")

        _, handler = self._format_map[fmt]
        return handler(package_path)
