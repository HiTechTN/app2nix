from unittest.mock import patch, MagicMock

import pytest

from app2nix.core.validator import validate_nix

VALID_NIX = "{ pkgs }: pkgs.hello"
INVALID_NIX = "this { is ;; not valid nix }"


# ── nix-instantiate succeeds ────────────────────────────────────────────────


def test_validate_valid_nix():
    """Valid Nix → returns (True, None)."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stderr = ""

    with patch("app2nix.core.validator.subprocess.run", return_value=mock):
        ok, err = validate_nix(VALID_NIX)

    assert ok is True
    assert err is None


def test_validate_valid_nix_passes_correct_args():
    """Verify the subprocess call uses correct command, input, and timeout."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stderr = ""

    with patch("app2nix.core.validator.subprocess.run", return_value=mock) as mock_run:
        validate_nix("test content", timeout=30)

    mock_run.assert_called_once_with(
        ["nix-instantiate", "--parse", "-"],
        input="test content",
        capture_output=True,
        text=True,
        timeout=30,
    )


# ── nix-instantiate fails (parse error) ─────────────────────────────────────


def test_validate_invalid_nix():
    """Invalid Nix → returns (False, stderr)."""
    mock = MagicMock()
    mock.returncode = 1
    mock.stderr = "syntax error at line 1"

    with patch("app2nix.core.validator.subprocess.run", return_value=mock):
        ok, err = validate_nix(INVALID_NIX)

    assert ok is False
    assert err == "syntax error at line 1"


def test_validate_invalid_nix_with_none_stderr():
    """Invalid Nix with stderr=None → returns (False, None)."""
    mock = MagicMock()
    mock.returncode = 2
    mock.stderr = None

    with patch("app2nix.core.validator.subprocess.run", return_value=mock):
        ok, err = validate_nix("bad nix")

    assert ok is False
    assert err is None


# ── nix-instantiate not found ────────────────────────────────────────────────


def test_validate_when_nix_not_installed():
    """nix-instantiate not found → returns (True, None) (skip validation)."""
    with patch(
        "app2nix.core.validator.subprocess.run",
        side_effect=FileNotFoundError("nix-instantiate not found"),
    ):
        ok, err = validate_nix(VALID_NIX)

    assert ok is True
    assert err is None


def test_validate_when_nix_not_installed_with_invalid_content():
    """nix-instantiate not found → returns (True, None) even for invalid content."""
    with patch(
        "app2nix.core.validator.subprocess.run",
        side_effect=FileNotFoundError("nix-instantiate not found"),
    ):
        ok, err = validate_nix(INVALID_NIX)

    assert ok is True
    assert err is None


# ── timeout ──────────────────────────────────────────────────────────────────


def test_validate_timeout():
    """subprocess timeout → propagates TimeoutExpired."""
    from subprocess import TimeoutExpired

    with patch(
        "app2nix.core.validator.subprocess.run",
        side_effect=TimeoutExpired("nix-instantiate", timeout=10),
    ):
        with pytest.raises(TimeoutExpired):
            validate_nix(VALID_NIX, timeout=10)
