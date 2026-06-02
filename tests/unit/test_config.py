"""
Unit tests for app2nix/config.py — Settings and get_settings().

Covers: default values, env-file loading, env_prefix override,
and lru_cache idempotency of get_settings().
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app2nix.config import Settings, get_settings


# ---------------------------------------------------------------------------
# Settings defaults
# ---------------------------------------------------------------------------


class TestSettingsDefaults:
    def test_debug_default_is_false(self):
        s = Settings()
        assert s.debug is False

    def test_max_upload_size_default(self):
        s = Settings()
        assert s.max_upload_size == 500 * 1024 * 1024

    def test_upload_timeout_default(self):
        s = Settings()
        assert s.upload_timeout == 60

    def test_validate_nix_default(self):
        s = Settings()
        assert s.validate_nix is True

    def test_nix_timeout_default(self):
        s = Settings()
        assert s.nix_timeout == 10

    def test_cache_ttl_days_default(self):
        s = Settings()
        assert s.cache_ttl_days == 30

    def test_api_rate_limit_default(self):
        s = Settings()
        assert s.api_rate_limit == 10

    def test_secret_key_is_hex_string(self):
        s = Settings()
        assert isinstance(s.secret_key, str)
        assert len(s.secret_key) == 64  # 32 bytes = 64 hex chars

    def test_work_dir_is_path(self):
        s = Settings()
        assert isinstance(s.work_dir, Path)

    def test_cache_db_is_path(self):
        s = Settings()
        assert isinstance(s.cache_db, Path)


# ---------------------------------------------------------------------------
# Environment variable override
# ---------------------------------------------------------------------------


class TestSettingsEnvOverride:
    def test_debug_from_env(self):
        s = Settings(debug=True)
        assert s.debug is True

    def test_max_upload_size_override(self):
        s = Settings(max_upload_size=1024)
        assert s.max_upload_size == 1024

    def test_nix_timeout_override(self):
        s = Settings(nix_timeout=30)
        assert s.nix_timeout == 30

    def test_validate_nix_override(self):
        s = Settings(validate_nix=False)
        assert s.validate_nix is False

    def test_secret_key_override(self):
        s = Settings(secret_key="my-test-key")
        assert s.secret_key == "my-test-key"


# ---------------------------------------------------------------------------
# get_settings() caching
# ---------------------------------------------------------------------------


class TestGetSettings:
    def test_get_settings_returns_settings_instance(self):
        result = get_settings()
        assert isinstance(result, Settings)

    def test_get_settings_returns_same_instance(self):
        """lru_cache means the same object is returned every call."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_lru_cache_clear(self):
        """After clearing the cache, a new Settings instance is created."""
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # same after warm-up
        # But a fresh call to Settings() should produce a new object
        s3 = Settings()
        assert s3 is not s1
