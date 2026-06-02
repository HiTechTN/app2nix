import pytest

from app2nix.core.resolver import DependencyResolver


@pytest.fixture
def resolver():
    return DependencyResolver()


# ── resolve_sync — edge cases ───────────────────────────────────────────────


class TestResolveSyncEdgeCases:
    def test_lib_prefix_stripped(self, resolver):
        """libssl → strip 'lib' → ssl → openssl"""
        r = resolver.resolve_sync("libssl")
        assert r.nixpkg == "openssl"
        assert r.confidence == 1.0
        assert r.source == "dict"

    def test_so_suffix_stripped(self, resolver):
        """libssl.so.3 → split on .so → libssl → strip lib → ssl → openssl"""
        r = resolver.resolve_sync("libssl.so.3")
        assert r.nixpkg == "openssl"

    def test_both_lib_prefix_and_so_suffix(self, resolver):
        r = resolver.resolve_sync("libGL.so.1")
        assert r.nixpkg == "libGL"

    def test_dotted_name_without_lib_prefix(self, resolver):
        r = resolver.resolve_sync("gtk-3.so.0")
        assert r.nixpkg == "gtk3"

    def test_unknown_lib_with_so_suffix(self, resolver):
        r = resolver.resolve_sync("libcompletely_unknown_lib.so.1")
        assert r.nixpkg is None
        assert r.source == "unknown"

    def test_fuzzy_match_with_so_suffix(self, resolver):
        """'libcairoo.so' → strip 'lib' + .so suffix → 'cairoo' → fuzzy matches 'cairo'"""
        r = resolver.resolve_sync("libcairoo.so.0")
        assert r.nixpkg == "cairo"
        assert r.confidence == 0.8
        assert r.source == "fuzzy"

    def test_fuzzy_no_match_with_low_cutoff(self, resolver):
        """'xy' is only 2 chars — should not match 'xz' at cutoff=0.8"""
        r = resolver.resolve_sync("xy")
        assert r.nixpkg is None
        assert r.source == "unknown"

    def test_long_unknown_name(self, resolver):
        r = resolver.resolve_sync("this_is_a_very_long_library_name_that_does_not_exist")
        assert r.nixpkg is None
        assert r.source == "unknown"


# ── resolve_all — edge cases ────────────────────────────────────────────────


class TestResolveAllExtended:
    def test_empty_list(self, resolver):
        resolved, unresolved = resolver.resolve_all([])
        assert resolved == []
        assert unresolved == []

    def test_all_known(self, resolver):
        resolved, unresolved = resolver.resolve_all(["ssl", "z", "cairo"])
        assert len(resolved) == 3
        assert unresolved == []

    def test_all_unknown(self, resolver):
        resolved, unresolved = resolver.resolve_all(["foo_unknown", "bar_unknown"])
        assert resolved == []
        assert len(unresolved) == 2

    def test_mixed_with_duplicates(self, resolver):
        resolved, unresolved = resolver.resolve_all(["ssl", "unknown_1", "z", "unknown_2"])
        assert resolved == ["openssl", "zlib"]
        assert unresolved == ["unknown_1", "unknown_2"]

    def test_deduplication(self, resolver):
        """Multiple libs resolving to the same nixpkg should be deduplicated."""
        resolved, unresolved = resolver.resolve_all(["avcodec", "avformat", "avutil"])
        assert resolved == ["ffmpeg"]
        assert unresolved == []
