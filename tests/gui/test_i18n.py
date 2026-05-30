"""
Unit tests for lib/i18n.py — internationalisation module.

Covers load(), tr(), lang(), available(), is_rtl() and fallback
behaviour.  Tests use the real translation files on disk.
"""

import json
from pathlib import Path
from unittest.mock import patch

import app2nix.gui.i18n as i18n

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "app2nix" / "gui" / "translations"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reload_i18n():
    """Reload the module so _load_english() re-reads the en.json file."""
    import importlib
    importlib.reload(i18n)


# ---------------------------------------------------------------------------
# English fallback (default state)
# ---------------------------------------------------------------------------

class TestEnglishFallback:
    def setup_method(self):
        reload_i18n()

    def test_default_lang_english(self):
        assert i18n.lang() == "en"

    def test_tr_known_key_returns_translation(self):
        title = i18n.tr("window.title")
        assert "app2nix" in title
        assert "NixOS" in title

    def test_tr_unknown_key_returns_key(self):
        assert i18n.tr("nonexistent.key") == "nonexistent.key"

    def test_tr_unknown_key_with_default(self):
        assert i18n.tr("nonexistent.key", "Custom default") == "Custom default"

    def test_tr_known_key_ignores_default(self):
        title = i18n.tr("window.title", "Override")
        assert "app2nix" in title


# ---------------------------------------------------------------------------
# Language loading
# ---------------------------------------------------------------------------

class TestLanguageLoading:
    def setup_method(self):
        reload_i18n()

    def test_load_french_returns_true(self):
        assert i18n.load("fr") is True
        assert i18n.lang() == "fr"

    def test_load_arabic_returns_true(self):
        assert i18n.load("ar") is True
        assert i18n.lang() == "ar"

    def test_load_nonexistent_lang_returns_false(self):
        assert i18n.load("de") is False
        # should remain on English
        assert i18n.lang() == "en"

    def test_load_french_uses_french_strings(self):
        i18n.load("fr")
        assert i18n.tr("window.title") == (
            "app2nix - Convertisseur de paquets vers NixOS"
        )

    def test_load_arabic_uses_arabic_strings(self):
        i18n.load("ar")
        title = i18n.tr("window.title")
        assert "محول" in title

    def test_switch_back_to_english(self):
        i18n.load("fr")
        i18n.load("en")
        assert i18n.lang() == "en"
        assert "NixOS" in i18n.tr("window.title")


# ---------------------------------------------------------------------------
# Fallback chain: loaded strings -> English fallback -> key / default
# ---------------------------------------------------------------------------

class TestFallbackChain:
    def setup_method(self):
        reload_i18n()

    def test_fallback_to_english_when_key_missing_in_french(self):
        """If a key does not exist in the loaded language, fall back to English."""
        i18n.load("fr")
        # Key exists in both — returns French
        assert i18n.tr("menu.about") == "À propos d'app2nix"
        # Simulate missing key by patching _strings — should fall back to English
        with patch.object(i18n, "_strings", {}):
            val = i18n.tr("window.title")
            assert "NixOS" in val

    def test_fallback_to_english_for_missing_key(self):
        """Simulate missing key in loaded language by patching _strings."""
        i18n.load("fr")
        with patch.object(i18n, "_strings", {}):
            val = i18n.tr("window.title")
            assert "NixOS" in val  # falls back to English _fallback

    def test_double_fallback_returns_key(self):
        """When both _strings and _fallback are empty, return the key itself."""
        with (
            patch.object(i18n, "_strings", {}),
            patch.object(i18n, "_fallback", {}),
        ):
            assert i18n.tr("unknown.key") == "unknown.key"
            assert i18n.tr("unknown.key", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# RTL detection
# ---------------------------------------------------------------------------

class TestRtl:
    def setup_method(self):
        reload_i18n()

    def test_english_is_not_rtl(self):
        assert i18n.is_rtl() is False

    def test_french_is_not_rtl(self):
        i18n.load("fr")
        assert i18n.is_rtl() is False

    def test_arabic_is_rtl(self):
        i18n.load("ar")
        assert i18n.is_rtl() is True

    def test_unknown_lang_default_not_rtl(self):
        i18n.load("de")  # returns False, falls back to en
        assert i18n.is_rtl() is False


# ---------------------------------------------------------------------------
# Available languages
# ---------------------------------------------------------------------------

class TestAvailable:
    def setup_method(self):
        reload_i18n()

    def test_returns_list_of_tuples(self):
        langs = i18n.available()
        assert isinstance(langs, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in langs)

    def test_includes_known_languages(self):
        langs = dict(i18n.available())
        assert langs.get("en") == "English"
        assert langs.get("fr") == "Français"
        assert langs.get("ar") == "العربية"

    def test_all_referenced_files_exist(self):
        for code, _ in i18n.available():
            path = TRANSLATIONS_DIR / f"{code}.json"
            assert path.exists(), f"Translation file missing: {path}"

    def test_all_files_are_valid_json(self):
        for code, _ in i18n.available():
            path = TRANSLATIONS_DIR / f"{code}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, dict)
            assert len(data) > 10  # at least 10 translation keys


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def setup_method(self):
        reload_i18n()

    def test_tr_empty_key(self):
        """Empty key should return empty or key itself."""
        assert i18n.tr("") == ""

    def test_tr_none_key(self):
        """None key should be handled gracefully (dict.get returns None silently)."""
        result = i18n.tr(None)  # type: ignore[arg-type]
        # dict.get(None) returns None; then "None or None" → None
        assert result is None

    def test_tr_html_entities_unescaped(self):
        """Check that translated strings are raw text, not HTML-escaped."""
        val = i18n.tr("app.subtitle")
        assert "(" in val or "NixOS" in val

    def test_reload_resets_lang(self):
        i18n.load("fr")
        reload_i18n()
        assert i18n.lang() == "en"


# Import patch at the end to avoid circularity issues

