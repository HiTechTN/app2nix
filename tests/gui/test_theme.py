"""
Unit tests for lib/theme.py — theme definitions and switching.

These tests cover the LIGHT/DARK colour dictionaries, the global theme
state management (set/get/name), and ensure all required keys exist.
"""


import lib.theme as theme


class TestThemeDictionaries:
    """Verify LIGHT and DARK dicts are complete and well-formed."""

    REQUIRED_KEYS = {
        "name", "bg", "card_bg", "card_border",
        "text_primary", "text_secondary", "text_muted",
        "input_bg", "input_border", "input_focus",
        "header_start", "header_end", "header_text", "header_subtitle",
        "accent", "accent_hover", "success", "success_hover",
        "btn_sec_bg", "btn_sec_text", "btn_sec_border", "btn_sec_hover",
        "code_bg", "code_text",
        "tab_bg", "tab_text", "tab_selected",
        "status_bg", "status_text",
        "menu_bg", "menu_text", "menu_hover",
        "progress_bg", "separator",
    }

    def test_light_has_all_keys(self):
        missing = self.REQUIRED_KEYS - theme.LIGHT.keys()
        assert not missing, f"LIGHT theme missing keys: {missing}"

    def test_dark_has_all_keys(self):
        missing = self.REQUIRED_KEYS - theme.DARK.keys()
        assert not missing, f"DARK theme missing keys: {missing}"

    def test_light_name(self):
        assert theme.LIGHT["name"] == "light"

    def test_dark_name(self):
        assert theme.DARK["name"] == "dark"

    def test_both_have_same_keys(self):
        assert set(theme.LIGHT.keys()) == set(theme.DARK.keys()), (
            "LIGHT and DARK must have identical key sets"
        )

    def test_all_exist_dict(self):
        assert "light" in theme.ALL
        assert "dark" in theme.ALL
        assert theme.ALL["light"] is theme.LIGHT
        assert theme.ALL["dark"] is theme.DARK


class TestThemeStateManagement:
    """Test the global module-level state set() / get() / name()."""

    def setup_method(self):
        # Reset to default before each test
        theme.set("light")

    def test_default_is_light(self):
        assert theme.name() == "light"
        assert theme.get() is theme.LIGHT

    def test_set_dark(self):
        theme.set("dark")
        assert theme.name() == "dark"
        assert theme.get() is theme.DARK

    def test_set_light(self):
        theme.set("light")
        assert theme.name() == "light"
        assert theme.get() is theme.LIGHT

    def test_set_unknown_leaves_current_unchanged(self):
        theme.set("dark")
        theme.set("pink")
        # Should still be dark
        assert theme.name() == "dark"

    def test_set_invalid_type_leaves_current(self):
        theme.set("light")
        theme.set(123)  # type: ignore[arg-type]
        assert theme.name() == "light"

    def test_get_returns_current_dict(self):
        theme.set("dark")
        d = theme.get()
        assert d["accent"] == "#60a5fa"
        assert d["bg"] == "#0f172a"

    def test_set_light_after_dark(self):
        theme.set("dark")
        theme.set("light")
        assert theme.get() is theme.LIGHT


class TestThemeIdempotency:
    """Switching to the same theme should not break anything."""

    def test_set_light_twice(self):
        theme.set("light")
        acc1 = theme.get()["accent"]
        theme.set("light")
        acc2 = theme.get()["accent"]
        assert acc1 == acc2

    def test_set_light_dark_light(self):
        theme.set("dark")
        theme.set("light")
        assert theme.name() == "light"

