import subprocess


def validate_nix(nix_content: str, timeout: int = 10) -> tuple[bool, str | None]:
    try:
        r = subprocess.run(
            ["nix-instantiate", "--parse", "-"],
            input=nix_content, capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, r.stderr if r.returncode != 0 else None
    except FileNotFoundError:
        return True, None
