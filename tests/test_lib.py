"""Tests for app2nix"""

from lib.deb_to_nix import translate, translate_all


def test_translate_libdrm():
    """Test translating libdrm -> libdrm"""
    assert translate("drm") == "libdrm"


def test_translate_gtk():
    """Test translating gtk-3 -> gtk3"""
    assert translate("gtk-3") == "gtk3"


def test_translate_alsa():
    """Test translating asound -> alsa-lib"""
    assert translate("asound") == "alsa-lib"


def test_translate_all():
    """Test translating multiple libraries"""
    libs = ["drm", "gtk-3", "X11", "asound"]
    result = translate_all(libs)
    assert "libdrm" in result
    assert "gtk3" in result
    assert "libX11" in result


def test_translate_unknown():
    """Test unknown library returns None"""
    assert translate("unknownlib") is None


def test_translate_all_with_unknown():
    """Test translate_all filters None results"""
    libs = ["drm", "unknownlib", "X11"]
    result = translate_all(libs)
    assert len(result) == 2
    assert "libdrm" in result
    assert "libX11" in result
    assert "unknownlib" not in result
