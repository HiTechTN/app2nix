"""Tests for app2nix dependency resolution."""

from app2nix.core.resolver import DEP_MAP


def test_translate_libdrm():
    assert DEP_MAP.get("drm") == "libdrm"


def test_translate_gtk():
    assert DEP_MAP.get("gtk-3") == "gtk3"


def test_translate_alsa():
    assert DEP_MAP.get("asound") == "alsa-lib"


def test_unknown_returns_none():
    assert DEP_MAP.get("unknownlib") is None
