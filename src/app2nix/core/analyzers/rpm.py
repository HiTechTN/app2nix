import subprocess
import tempfile
from pathlib import Path

from app2nix.core.analyzers._elf_utils import extract_lib_name, find_elf, get_libs_patchelf
from app2nix.models import PackageInfo


def _parse_rpm_filename(stem: str) -> tuple[str, str, str]:
    import re
    arch_map = {
        "x86_64", "amd64", "i386", "i686", "aarch64", "arm64",
        "armv7hl", "armv7hnl", "armv6hl", "noarch", "ppc64le", "s390x",
    }
    parts = stem.rsplit(".", 1)
    arch = parts[1] if len(parts) == 2 and parts[1] in arch_map else "x86_64"
    rest = parts[0]
    # RPM filename format: name-version-release
    # Split from the right: last component is release, next is version-possibly-with-dashes
    # Try to find version by looking for digit-starting segment from the right
    segments = rest.rsplit("-", 2)
    if len(segments) == 3:
        candidate_verrel = segments[1] + "-" + segments[2]
        # Try splitting candidate_verrel into version-release
        verrel_parts = candidate_verrel.rsplit("-", 1)
        if len(verrel_parts) == 2 and (verrel_parts[1].isdigit() or re.match(r'^\d', verrel_parts[1])):
            name = segments[0]
            version = verrel_parts[0]
        else:
            name, version = segments[0], candidate_verrel
    elif len(segments) == 2:
        name = segments[0]
        version = segments[1]
    else:
        name = segments[0]
        version = "1.0"
    return name, version, arch


def _find_rpm() -> str:
    """Locate rpm binary."""
    import shutil
    path = shutil.which("rpm")
    if path:
        return path
    try:
        result = subprocess.run(
            ["nix", "shell", "nixpkgs#rpm", "-c", "which", "rpm"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def analyze_rpm(rpm_path: str) -> PackageInfo:
    path = Path(rpm_path)
    name, version, arch = path.stem, "1.0", "x86_64"

    rpm_bin = _find_rpm()
    if rpm_bin:
        try:
            info_out = subprocess.check_output(
                [rpm_bin, "-qp", "--queryformat", "%{NAME}\\t%{VERSION}\\t%{ARCH}\\n", rpm_path],
                stderr=subprocess.DEVNULL, text=True,
            )
            parts = info_out.strip().split("\t")
            if len(parts) == 3:
                name, version, arch = parts
        except (subprocess.CalledProcessError, FileNotFoundError):
            name, version, arch = _parse_rpm_filename(path.stem)

    deps: list[str] = []
    if rpm_bin:
        try:
            req_out = subprocess.check_output(
                [rpm_bin, "-qp", "--requires", rpm_path],
                stderr=subprocess.DEVNULL, text=True,
            )
            for line in req_out.splitlines():
                lib = line.strip().split()[0]
                name_only = extract_lib_name(lib)
                if name_only:
                    deps.append(name_only)
        except (subprocess.CalledProcessError, FileNotFoundError):
            deps = _extract_deps_via_cpio(rpm_path)
    else:
        deps = _extract_deps_via_cpio(rpm_path)

    return PackageInfo(
        name=name,
        version=version,
        architecture=arch,
        format="rpm",
        dependencies=sorted(set(deps)),
        executables=[],
    )


def _find_rpm2cpio() -> str:
    """Locate rpm2cpio binary."""
    import shutil
    path = shutil.which("rpm2cpio")
    if path:
        return path
    # Try via nix shell
    try:
        result = subprocess.run(
            ["nix", "shell", "nixpkgs#rpm", "-c", "which", "rpm2cpio"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def _extract_deps_via_cpio(rpm_path: str) -> list[str]:
    deps: set[str] = set()
    rpm2cpio_bin = _find_rpm2cpio()
    if not rpm2cpio_bin:
        return sorted(deps)
    with tempfile.TemporaryDirectory(prefix="app2nix_rpm_") as tmpdir:
        try:
            cpio_proc = subprocess.Popen(
                [rpm2cpio_bin, rpm_path],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["cpio", "-idmv"],
                stdin=cpio_proc.stdout,
                cwd=tmpdir, capture_output=True,
            )
            cpio_proc.wait()
            for elf in find_elf(Path(tmpdir)):
                deps.update(get_libs_patchelf(elf))
        except FileNotFoundError:
            pass
    return sorted(deps)
