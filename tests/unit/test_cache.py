import sqlite3
from datetime import datetime, timedelta

import pytest

from app2nix.cache import DepCache


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_cache.db"


@pytest.fixture
def cache(db_path):
    return DepCache(db_path)


# ── Initialisation ──────────────────────────────────────────────────────────


def test_init_creates_db_file(db_path):
    assert not db_path.exists()
    DepCache(db_path)
    assert db_path.exists()


def test_init_creates_parent_directory(tmp_path):
    nested = tmp_path / "sub" / "dir" / "cache.db"
    assert not nested.parent.exists()
    DepCache(nested)
    assert nested.exists()


def test_init_creates_tables(cache):
    with sqlite3.connect(cache.db_path) as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    assert "resolved" in tables


def test_init_idempotent(cache):
    """Calling __init__ twice should not raise."""
    DepCache(cache.db_path)  # second init on same file


# ── get / set — basic roundtrip ─────────────────────────────────────────────


def test_get_returns_none_for_missing_key(cache):
    assert cache.get("nonexistent") is None


def test_set_and_get(cache):
    cache.set("libfoo", "foo", "dict", 1.0)
    result = cache.get("libfoo")
    assert result == ("foo", "dict", 1.0)


def test_get_returns_none_after_set_on_different_key(cache):
    cache.set("libbar", "bar", "dict", 0.9)
    assert cache.get("libfoo") is None


def test_set_overwrites_existing(cache):
    cache.set("libx", "old_pkg", "dict", 0.5)
    cache.set("libx", "new_pkg", "fuzzy", 0.9)
    result = cache.get("libx")
    assert result == ("new_pkg", "fuzzy", 0.9)


def test_set_updates_cached_at(cache):
    cache.set("liby", "ypkg", "dict", 1.0)
    with sqlite3.connect(cache.db_path) as db:
        row = db.execute(
            "SELECT cached_at FROM resolved WHERE lib_name = ?", ("liby",)
        ).fetchone()
    assert row is not None
    assert row[0] is not None  # cached_at should be set


def test_set_with_special_chars_in_lib_name(cache):
    cache.set("lib-2.4_rc1+debug", "mypkg", "dict", 0.8)
    assert cache.get("lib-2.4_rc1+debug") == ("mypkg", "dict", 0.8)


# ── clear_expired ───────────────────────────────────────────────────────────


def test_clear_expired_empty_cache(cache):
    """Clearing an empty cache should not raise."""
    cache.clear_expired(ttl_days=1)
    assert cache.get("anything") is None


def test_clear_expired_keeps_fresh_entries(cache):
    cache.set("fresh_lib", "fpkg", "dict", 1.0)
    cache.clear_expired(ttl_days=30)
    assert cache.get("fresh_lib") == ("fpkg", "dict", 1.0)


def test_clear_expired_removes_old_entries(cache):
    cache.set("old_lib", "opkg", "dict", 1.0)
    # Manually backdate the entry so it's older than TTL
    old_ts = (datetime.now() - timedelta(days=60)).isoformat()
    with sqlite3.connect(cache.db_path) as db:
        db.execute(
            "UPDATE resolved SET cached_at = ? WHERE lib_name = ?",
            (old_ts, "old_lib"),
        )
    cache.clear_expired(ttl_days=30)
    assert cache.get("old_lib") is None


def test_clear_expired_mixed_entries(cache):
    """Fresh entries survive; old entries are removed."""
    cache.set("fresh", "fpkg", "dict", 1.0)
    cache.set("old", "opkg", "dict", 0.5)

    old_ts = (datetime.now() - timedelta(days=90)).isoformat()
    with sqlite3.connect(cache.db_path) as db:
        db.execute("UPDATE resolved SET cached_at = ? WHERE lib_name = ?", (old_ts, "old"))

    cache.clear_expired(ttl_days=30)

    assert cache.get("fresh") == ("fpkg", "dict", 1.0)
    assert cache.get("old") is None


def test_clear_expired_custom_ttl(cache):
    cache.set("test_lib", "tpkg", "dict", 1.0)
    old_ts = (datetime.now() - timedelta(hours=2)).isoformat()
    with sqlite3.connect(cache.db_path) as db:
        db.execute(
            "UPDATE resolved SET cached_at = ? WHERE lib_name = ?",
            (old_ts, "test_lib"),
        )
    # TTL of 1 day — entry is 2 hours old, should survive
    cache.clear_expired(ttl_days=1)
    assert cache.get("test_lib") is not None

    # TTL of 0 days — entry is 2 hours old, should be removed
    cache.clear_expired(ttl_days=0)
    assert cache.get("test_lib") is None


# ── Multiple entries ────────────────────────────────────────────────────────


def test_multiple_independent_entries(cache):
    entries = {
        "lib_a": ("pkg_a", "dict", 0.9),
        "lib_b": ("pkg_b", "fuzzy", 0.7),
        "lib_c": ("pkg_c", "dict", 1.0),
    }
    for name, (pkg, src, conf) in entries.items():
        cache.set(name, pkg, src, conf)

    for name, (pkg, src, conf) in entries.items():
        assert cache.get(name) == (pkg, src, conf)


# ── Persistence across instances ────────────────────────────────────────────


def test_cache_persists_across_instances(db_path):
    cache1 = DepCache(db_path)
    cache1.set("persist_lib", "ppkg", "dict", 1.0)

    cache2 = DepCache(db_path)
    assert cache2.get("persist_lib") == ("ppkg", "dict", 1.0)


def test_clear_expired_persists_changes(db_path):
    cache1 = DepCache(db_path)
    cache1.set("old_lib", "opkg", "dict", 1.0)
    old_ts = (datetime.now() - timedelta(days=60)).isoformat()
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE resolved SET cached_at = ? WHERE lib_name = ?",
            (old_ts, "old_lib"),
        )

    cache2 = DepCache(db_path)
    cache2.clear_expired(ttl_days=30)

    cache3 = DepCache(db_path)
    assert cache3.get("old_lib") is None
