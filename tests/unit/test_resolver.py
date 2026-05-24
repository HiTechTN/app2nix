
import pytest

from app2nix.core.resolver import DependencyResolver


@pytest.fixture
def resolver(tmp_path):
    return DependencyResolver(tmp_path / "test_cache.db")


def test_resolve_known_lib(resolver):
    r = resolver.resolve_sync("ssl")
    assert r.nixpkg == "openssl"
    assert r.confidence == 1.0
    assert r.source == "dict"


def test_resolve_unknown_lib(resolver):
    r = resolver.resolve_sync("totally_unknown_xyz_lib_2025")
    assert r.nixpkg is None
    assert r.source == "unknown"


def test_resolve_all_returns_two_lists(resolver):
    resolved, unresolved = resolver.resolve_all(["ssl", "z", "unknown_xyz"])
    assert "openssl" in resolved
    assert "zlib" in resolved
    assert "unknown_xyz" in unresolved


def test_resolve_fuzzy_match(resolver):
    r = resolver.resolve_sync("cairo_")
    assert r.nixpkg is not None
    assert r.confidence == 0.8
    assert r.source == "fuzzy"
