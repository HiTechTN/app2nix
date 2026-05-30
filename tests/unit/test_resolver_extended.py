import pytest

from app2nix.core.resolver import DependencyResolver


@pytest.fixture
def resolver(tmp_path):
    return DependencyResolver(tmp_path / "test_cache.db")


# ── _init_cache exception path ──────────────────────────────────────────────


def test_init_cache_handles_db_error(tmp_path):
    """_init_cache should catch and ignore DB errors gracefully."""
    # Create a file at the path where we want the DB, then point cache_path
    # at an existing directory so sqlite3.connect fails.
    db_dir = tmp_path / "db_dir"
    db_dir.mkdir()
    resolver = DependencyResolver(db_dir)
    # Should not raise — the except Exception: pass handles it
    # Cache was initialized (DB creation failed silently)
    assert resolver.cache_path == db_dir


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


# ── resolve_async — known lib (returns early) ───────────────────────────────


@pytest.mark.asyncio
async def test_resolve_async_known_lib(resolver):
    """Known lib should return sync result immediately without HTTP call."""
    r = await resolver.resolve_async("ssl")
    assert r.nixpkg == "openssl"
    assert r.confidence == 1.0
    assert r.source == "dict"


# ── resolve_async — unknown lib, mocked httpx ───────────────────────────────


@pytest.mark.asyncio
async def test_resolve_async_api_hit_found(resolver):
    """Unknown lib → API returns a hit → result with source='api'."""
    mock_response = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "package_attr_name": "mocked_pkg",
                    }
                }
            ]
        }
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_response

    class MockClient:
        def __init__(self):
            self._request = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            self._request = (method, url, kwargs)
            return MockResponse()

    class MockHttpx:
        AsyncClient = lambda self, **kw: MockClient()  # noqa: E731

    import sys
    sys.modules["httpx"] = MockHttpx()

    try:
        r = await resolver.resolve_async("unknown_lib_for_testing")
        assert r.nixpkg == "mocked_pkg"
        assert r.confidence == 0.6
        assert r.source == "api"
    finally:
        del sys.modules["httpx"]


@pytest.mark.asyncio
async def test_resolve_async_api_no_hits(resolver):
    """Unknown lib → API returns no hits → falls back to sync result (unknown)."""
    mock_response = {"hits": {"hits": []}}

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_response

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            return MockResponse()

    class MockHttpx:
        AsyncClient = lambda self, **kw: MockClient()  # noqa: E731

    import sys
    sys.modules["httpx"] = MockHttpx()

    try:
        r = await resolver.resolve_async("unknown_lib_no_hits")
        assert r.nixpkg is None
        assert r.source == "unknown"
    finally:
        del sys.modules["httpx"]


@pytest.mark.asyncio
async def test_resolve_async_api_error(resolver):
    """Unknown lib → API returns non-200 → falls back to sync result."""
    class MockResponse:
        status_code = 500

        def json(self):
            return {}

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            return MockResponse()

    class MockHttpx:
        AsyncClient = lambda self, **kw: MockClient()  # noqa: E731

    import sys
    sys.modules["httpx"] = MockHttpx()

    try:
        r = await resolver.resolve_async("unknown_lib_error")
        assert r.nixpkg is None
        assert r.source == "unknown"
    finally:
        del sys.modules["httpx"]


@pytest.mark.asyncio
async def test_resolve_async_network_exception(resolver):
    """Unknown lib → network exception → caught silently → falls back to sync result."""

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            raise ConnectionError("Network timeout")

    class MockHttpx:
        AsyncClient = lambda self, **kw: MockClient()  # noqa: E731

    import sys
    sys.modules["httpx"] = MockHttpx()

    try:
        r = await resolver.resolve_async("unknown_lib_network_error")
        assert r.nixpkg is None
        assert r.source == "unknown"
    finally:
        del sys.modules["httpx"]
