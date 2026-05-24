import subprocess
import tempfile
from pathlib import Path

from app2nix.models import PackageInfo


def analyze_rpm(rpm_path: str) -> PackageInfo:
    path = Path(rpm_path)
    name, version, arch = path.stem, "1.0", "x86_64"

    try:
        info_out = subprocess.check_output(
            ["rpm", "-qp", "--queryformat", "%{NAME}\\t%{VERSION}\\t%{ARCH}\\n", rpm_path],
            stderr=subprocess.DEVNULL, text=True,
        )
        parts = info_out.strip().split("\t")
        if len(parts) == 3:
            name, version, arch = parts
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    deps: list[str] = []
    try:
        req_out = subprocess.check_output(
            ["rpm", "-qp", "--requires", rpm_path],
            stderr=subprocess.DEVNULL, text=True,
        )
        for line in req_out.splitlines():
            lib = line.strip().split()[0]
            if lib.startswith("lib") and ".so" in lib:
                name_only = lib[3:].split(".so")[0]
                if name_only:
                    deps.append(name_only)
    except (subprocess.CalledProcessError, FileNotFoundError):
        deps = _extract_deps_via_cpio(rpm_path)

    return PackageInfo(
        name=name,
        version=version,
        architecture=arch,
        format="rpm",
        dependencies=sorted(set(deps)),
        executables=[],
    )


def _extract_deps_via_cpio(rpm_path: str) -> list[str]:
    deps: list[str] = []
    with tempfile.TemporaryDirectory(prefix="app2nix_rpm_") as tmpdir:
        try:
            cpio_proc = subprocess.Popen(
                ["rpm2cpio", rpm_path],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["cpio", "-idmv"],
                stdin=cpio_proc.stdout,
                cwd=tmpdir, capture_output=True,
            )
            cpio_proc.wait()
            for f in Path(tmpdir).rglob("*"):
                if f.is_file() and not f.is_symlink():
                    try:
                        r = subprocess.run(
                            ["patchelf", "--print-needed", str(f)],
                            capture_output=True, text=True, timeout=5,
                        )
                        for lib in r.stdout.splitlines():
                            lib = lib.strip()
                            if lib.startswith("lib") and ".so" in lib:
                                name_only = lib[3:].split(".so")[0]
                                if name_only:
                                    deps.append(name_only)
                    except Exception:
                        pass
        except FileNotFoundError:
            pass
    return deps
