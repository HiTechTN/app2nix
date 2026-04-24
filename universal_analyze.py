#!/usr/bin/env python3
"""
Universal package analyzer - supports multiple formats.
Supported formats: .deb, .rpm, .AppImage, .tar.gz, .flatpak, .snap
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class PackageAnalyzer:
    """Analyze various package formats and extract dependencies."""

    FORMATS = [".deb", ".rpm", ".AppImage", ".tar", ".tar.gz", ".tgz", ".flatpak", ".snap"]

    def __init__(self, work_dir: str | None = None):
        self.work_dir = Path(work_dir or tempfile.mkdtemp(prefix="app2nix_"))
        self.temp_dirs = []

    def cleanup(self):
        """Clean up temporary directories."""
        for d in self.temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def analyze(self, package_path: str) -> dict:
        """Analyze package and return metadata."""
        path = Path(package_path)

        if not path.exists():
            raise FileNotFoundError(f"Package not found: {package_path}")

        suffix = path.suffix.lower()
        if suffix in [".tar", ".gz"]:
            suffix = ".tar.gz"

        handlers = {
            ".deb": self._analyze_deb,
            ".rpm": self._analyze_rpm,
            ".appimage": self._analyze_appimage,
            ".tar.gz": self._analyze_tar,
            ".tgz": self._analyze_tar,
            ".flatpak": self._analyze_flatpak,
            ".snap": self._analyze_snap,
        }

        handler = handlers.get(suffix)
        if not handler:
            raise ValueError(f"Unsupported format: {suffix}")

        return handler(path)

    def _analyze_deb(self, path: Path) -> dict:
        """Analyze .deb package."""
        temp_dir = self.work_dir / "deb_extracted"
        temp_dir.mkdir(exist_ok=True)
        self.temp_dirs.append(temp_dir)

        subprocess.run(["dpkg-deb", "-x", str(path), str(temp_dir)], check=True, capture_output=True)

        result = subprocess.run(["dpkg-deb", "-I", str(path)], capture_output=True, text=True)

        info = {
            "format": "deb",
            "name": "unknown",
            "version": "unknown",
            "architecture": "amd64",
            "dependencies": [],
            "binaries": [],
            "temp_dir": str(temp_dir)
        }

        for line in result.stdout.splitlines():
            if line.startswith("Package:"):
                info["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                info["version"] = line.split(":", 1)[1].strip()
            elif line.startswith("Architecture:"):
                info["architecture"] = line.split(":", 1)[1].strip()
            elif line.startswith("Depends:"):
                deps = line.split(":", 1)[1].strip()
                info["dependencies"] = self._parse_deb_deps(deps)

        info["binaries"] = self._find_binaries(temp_dir)
        info["libraries"] = self._find_libraries(temp_dir)

        return info

    def _analyze_rpm(self, path: Path) -> dict:
        """Analyze .rpm package."""
        temp_dir = self.work_dir / "rpm_extracted"
        temp_dir.mkdir(exist_ok=True)
        self.temp_dirs.append(temp_dir)

        subprocess.run(["rpm2cpio", str(path), "cpio", "-idmv", "-D", str(temp_dir)],
                     capture_output=True, shell=True)

        result = subprocess.run(["rpm", "-qip", str(path)], capture_output=True, text=True)

        info = {
            "format": "rpm",
            "name": "unknown",
            "version": "unknown",
            "architecture": "x86_64",
            "dependencies": [],
            "binaries": [],
            "temp_dir": str(temp_dir)
        }

        for line in result.stdout.splitlines():
            if line.startswith("Name:"):
                info["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                info["version"] = line.split(":", 1)[1].strip()
            elif line.startswith("Architecture:"):
                info["architecture"] = line.split(":", 1)[1].strip()
            elif line.startswith("Requires:"):
                deps = line.split(":", 1)[1].strip()
                info["dependencies"] = self._parse_rpm_deps(deps)

        info["binaries"] = self._find_binaries(temp_dir)
        info["libraries"] = self._find_libraries(temp_dir)

        return info

    def _analyze_appimage(self, path: Path) -> dict:
        """Analyze AppImage."""
        temp_dir = self.work_dir / "appimage_extracted"
        temp_dir.mkdir(exist_ok=True)
        self.temp_dirs.append(temp_dir)

        subprocess.run([str(path), "--appimage-extract"], cwd=temp_dir, capture_output=True)

        squashfs = temp_dir / "squashfs-root"
        if squashfs.exists():
            info = {
                "format": "AppImage",
                "name": path.stem.replace(".AppImage", ""),
                "version": "1.0",
                "architecture": "x86_64",
                "dependencies": [],
                "binaries": self._find_binaries(squashfs),
                "temp_dir": str(squashfs)
            }
            info["libraries"] = self._find_libraries(squashfs)
        else:
            raise ValueError("Failed to extract AppImage")

        return info

    def _analyze_tar(self, path: Path) -> dict:
        """Analyze tarball."""
        temp_dir = self.work_dir / "tar_extracted"
        temp_dir.mkdir(exist_ok=True)
        self.temp_dirs.append(temp_dir)

        subprocess.run(["tar", "-xf", str(path), "-C", str(temp_dir)], capture_output=True)

        info = {
            "format": "tar",
            "name": path.stem.replace(".tar.gz", "").replace(".tgz", ""),
            "version": "1.0",
            "architecture": "x86_64",
            "dependencies": [],
            "binaries": self._find_binaries(temp_dir),
            "temp_dir": str(temp_dir)
        }
        info["libraries"] = self._find_libraries(temp_dir)

        return info

    def _analyze_flatpak(self, path: Path) -> dict:
        """Analyze Flatpak."""
        result = subprocess.run(["flatpak-builder", "--show-manifest", str(path)],
                               capture_output=True, text=True)

        info = {
            "format": "flatpak",
            "name": path.stem.replace(".flatpak", ""),
            "version": "1.0",
            "architecture": "x86_64",
            "dependencies": [],
            "runtime": "unknown",
            "sdk": "unknown"
        }

        try:
            data = json.loads(result.stdout)
            info["name"] = data.get("id", info["name"])
            info["runtime"] = data.get("runtime", "unknown")
            info["sdk"] = data.get("sdk", "unknown")
        except Exception:
            pass

        return info

    def _analyze_snap(self, path: Path) -> dict:
        """Analyze Snap."""
        subprocess.run(["unsquashfs", "-l", str(path)], capture_output=True, text=True)

        info = {
            "format": "snap",
            "name": path.stem.replace(".snap", ""),
            "version": "1.0",
            "architecture": "x86_64",
            "dependencies": [],
            "temp_dir": str(self.work_dir / "snap")
        }

        return info

    def _parse_deb_deps(self, deps: str) -> list[str]:
        """Parse Debian dependencies."""
        result = []
        for dep in deps.split(","):
            dep = dep.strip().split(" ")[0]
            if dep:
                result.append(dep)
        return result

    def _parse_rpm_deps(self, deps: str) -> list[str]:
        """Parse RPM dependencies."""
        result = []
        for dep in deps.split():
            dep = dep.strip()
            if dep and not dep.startswith("rpmlib"):
                result.append(dep)
        return result

    def _find_binaries(self, directory: Path) -> list[str]:
        """Find ELF binaries."""
        binaries = []
        for root, _, files in os.walk(directory):
            for f in files:
                path = Path(root) / f
                if path.is_file():
                    try:
                        result = subprocess.run(["file", "-b", str(path)],
                                             capture_output=True, text=True)
                        if "ELF" in result.stdout and ("executable" in result.stdout or
                            "shared object" in result.stdout):
                            binaries.append(str(path.relative_to(directory)))
                    except:
                        pass
        return binaries

    def _find_libraries(self, directory: Path) -> list[str]:
        """Find shared libraries."""
        libraries = set()
        for root, _, files in os.walk(directory):
            for f in files:
                if f.endswith(".so"):
                    libraries.add(f)
        return sorted(list(libraries))


def main():
    parser = argparse.ArgumentParser(description="Universal package analyzer")
    parser.add_argument("package", help="Package file to analyze")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    analyzer = PackageAnalyzer()
    try:
        info = analyzer.analyze(args.package)

        output = json.dumps(info, indent=2)

        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Analyzed: {args.output}")
        else:
            print(output)

        if args.verbose:
            print(f"\nFormat: {info['format']}")
            print(f"Binaries found: {len(info['binaries'])}")
            print(f"Libraries found: {len(info.get('libraries', []))}")
    finally:
        analyzer.cleanup()


if __name__ == "__main__":
    main()
