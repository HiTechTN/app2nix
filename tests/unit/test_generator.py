import subprocess
from unittest.mock import patch

import pytest

from app2nix.core.generator import NixGenerator, _arch_to_nix_platform
from app2nix.models import PackageInfo


@pytest.fixture
def generator():
    return NixGenerator()


@pytest.fixture
def sample_deb_info():
    return PackageInfo(
        name="test-app",
        version="1.2.3",
        architecture="amd64",
        format="deb",
        dependencies=["ssl", "z", "curl"],
        description="Test application",
    )


def test_generate_default_nix_valid_syntax(generator, sample_deb_info):
    result = generator.generate_default_nix(sample_deb_info)
    assert result.nix_content
    assert "mkDerivation" in result.nix_content
    assert "autoPatchelfHook" in result.nix_content
    assert "makeSetupHook" not in result.nix_content


def test_generate_default_nix_no_broken_template(generator, sample_deb_info):
    result = generator.generate_default_nix(sample_deb_info)
    assert "{{" not in result.nix_content
    assert "{%" not in result.nix_content


def test_generate_flake_nix(generator, sample_deb_info):
    result = generator.generate_flake_nix(sample_deb_info)
    assert result.nix_content
    assert "flake-utils" in result.nix_content
    assert sample_deb_info.name in result.nix_content


def test_nix_name_sanitization():
    info = PackageInfo(name="My App (64-bit)!", version="1.0", format="deb")
    assert " " not in info.name
    assert "(" not in info.name


def test_validate_when_nix_not_installed(generator):
    """When nix-instantiate is not installed, validate() should return (True, None)."""
    with patch.object(subprocess, "run", side_effect=FileNotFoundError("nix-instantiate not found")):
        validated, err = generator.validate("some random content")

    assert validated is True
    assert err is None


def test_validate_success(generator):
    """When nix-instantiate succeeds, validate() should return (True, None)."""
    with patch.object(subprocess, "run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        validated, err = generator.validate("{ nix-expression = true; }")

    assert validated is True
    assert err is None


def test_validate_failure(generator):
    """When nix-instantiate fails with stderr, validate() should return (False, error)."""
    with patch.object(subprocess, "run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "syntax error at line 1"
        validated, err = generator.validate("invalid nix")

    assert validated is False
    assert err == "syntax error at line 1"


# =============================================================================
# _arch_to_nix_platform (pure function)
# =============================================================================


class TestArchToNixPlatform:
    def test_amd64(self):
        assert _arch_to_nix_platform("amd64") == "x86_64-linux"

    def test_x86_64(self):
        assert _arch_to_nix_platform("x86_64") == "x86_64-linux"

    def test_arm64(self):
        assert _arch_to_nix_platform("arm64") == "aarch64-linux"

    def test_aarch64(self):
        assert _arch_to_nix_platform("aarch64") == "aarch64-linux"

    def test_armhf(self):
        assert _arch_to_nix_platform("armhf") == "armv7l-linux"

    def test_armv7l(self):
        assert _arch_to_nix_platform("armv7l") == "armv7l-linux"

    def test_i386(self):
        assert _arch_to_nix_platform("i386") == "i686-linux"

    def test_i686(self):
        assert _arch_to_nix_platform("i686") == "i686-linux"

    def test_none_defaults_to_x86_64(self):
        assert _arch_to_nix_platform(None) == "x86_64-linux"

    def test_empty_string_defaults_to_x86_64(self):
        assert _arch_to_nix_platform("") == "x86_64-linux"

    def test_unknown_arch_defaults_to_x86_64(self):
        assert _arch_to_nix_platform("sparc64") == "x86_64-linux"

    def test_case_insensitive(self):
        assert _arch_to_nix_platform("AMD64") == "x86_64-linux"
        assert _arch_to_nix_platform("ARM64") == "aarch64-linux"
        assert _arch_to_nix_platform("Arm64") == "aarch64-linux"

    def test_all_known_architectures(self):
        """Every key in ARCH_TO_NIX_PLATFORM should map correctly."""
        from app2nix.core.generator import ARCH_TO_NIX_PLATFORM

        for arch, expected in ARCH_TO_NIX_PLATFORM.items():
            assert _arch_to_nix_platform(arch) == expected, f"{arch} -> {expected}"
            # Also verify case-insensitive
            assert _arch_to_nix_platform(arch.upper()) == expected, f"{arch.upper()} -> {expected}"
