import pytest

from app2nix.core.generator import NixGenerator
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
