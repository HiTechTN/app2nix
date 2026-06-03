#!/usr/bin/env python3
"""app2nix Android — Kivy-based GUI for converting Linux packages to NixOS expressions."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")

from kivy.app import App
from kivy.clock import mainthread
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import BooleanProperty, DictProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView

_project_root = Path(__file__).resolve().parent.parent / "src"
if _project_root.is_dir():
    sys.path.insert(0, str(_project_root))

from app2nix.core.analyzer import UniversalAnalyzer, detect_format
from app2nix.core.generator import NixGenerator
from app2nix.core.resolver import DependencyResolver

# ── Theme palettes ────────────────────────────────────────────────────
LIGHT: dict[str, list[float]] = {
    "bg": [0.94, 0.95, 0.96, 1],
    "card_bg": [1, 1, 1, 1],
    "text_primary": [0.10, 0.10, 0.18, 1],
    "text_secondary": [0.39, 0.45, 0.55, 1],
    "accent": [0.23, 0.51, 0.96, 1],
    "success": [0.10, 0.42, 0.24, 1],
    "code_bg": [0.12, 0.12, 0.18, 1],
    "code_text": [0.80, 0.84, 0.96, 1],
    "input_bg": [1, 1, 1, 1],
    "input_border": [0.82, 0.84, 0.86, 1],
    "header_bg": [0.12, 0.23, 0.37, 1],
    "header_text": [1, 1, 1, 1],
    "btn_sec_bg": [0.94, 0.95, 0.96, 1],
    "btn_sec_text": [0.22, 0.25, 0.32, 1],
}
DARK: dict[str, list[float]] = {
    "bg": [0.06, 0.10, 0.16, 1],
    "card_bg": [0.12, 0.16, 0.22, 1],
    "text_primary": [0.88, 0.91, 0.94, 1],
    "text_secondary": [0.58, 0.64, 0.72, 1],
    "accent": [0.38, 0.65, 0.98, 1],
    "success": [0.13, 0.77, 0.37, 1],
    "code_bg": [0.06, 0.10, 0.16, 1],
    "code_text": [0.65, 0.95, 0.98, 1],
    "input_bg": [0.12, 0.16, 0.22, 1],
    "input_border": [0.28, 0.33, 0.41, 1],
    "header_bg": [0.06, 0.10, 0.16, 1],
    "header_text": [0.94, 0.96, 0.97, 1],
    "btn_sec_bg": [0.20, 0.25, 0.33, 1],
    "btn_sec_text": [0.88, 0.91, 0.94, 1],
}

# ── KV layout ─────────────────────────────────────────────────────────
KV = r"""
#:import dp kivy.utils.dp

<DarkCard@BoxLayout>:
    orientation: 'vertical'
    padding: dp(16)
    spacing: dp(12)
    canvas.before:
        Color:
            rgba: app.t['card_bg']
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

<SectionLabel@Label>:
    font_size: sp(13)
    bold: True
    color: app.t['text_secondary']
    size_hint_y: None
    height: dp(24)
    text_size: self.size
    halign: 'left'
    valign: 'middle'

<MonoInput@TextInput>:
    font_size: sp(13)
    background_color: app.t['code_bg']
    foreground_color: app.t['code_text']
    cursor_color: app.t['accent']
    size_hint_y: None
    height: dp(140)
    padding: [dp(12), dp(8)]
    multiline: True
    readonly: True
    border: (0, 0, 0, 0)
    canvas.before:
        Color:
            rgba: app.t['code_bg']
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<AppButton@Button>:
    font_size: sp(14)
    bold: True
    size_hint_y: None
    height: dp(44)
    background_color: (0, 0, 0, 0)
    color: (1, 1, 1, 1)
    canvas.before:
        Color:
            rgba: app.t['accent']
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<SecButton@Button>:
    font_size: sp(14)
    size_hint_y: None
    height: dp(44)
    background_color: (0, 0, 0, 0)
    color: app.t['btn_sec_text']
    canvas.before:
        Color:
            rgba: app.t['btn_sec_bg']
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<SecInput@TextInput>:
    font_size: sp(14)
    size_hint_y: None
    height: dp(44)
    padding: [dp(12), dp(10)]
    background_color: app.t['input_bg']
    foreground_color: app.t['text_primary']
    cursor_color: app.t['accent']
    canvas.before:
        Color:
            rgba: app.t['input_border']
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(8))
            width: dp(1)

<TopBar@BoxLayout>:
    size_hint_y: None
    height: dp(56)
    padding: [dp(16), dp(8)]
    canvas.before:
        Color:
            rgba: app.t['header_bg']
        Rectangle:
            pos: self.pos
            size: self.size
    Label:
        text: 'app2nix'
        font_size: sp(18)
        bold: True
        color: app.t['header_text']
        size_hint_x: 0.8
        text_size: self.size
        halign: 'left'
        valign: 'middle'
    Button:
        text: app.theme_icon
        font_size: sp(18)
        size_hint_x: 0.2
        background_color: (0, 0, 0, 0)
        on_release: app.toggle_theme()

MainLayout:
    orientation: 'vertical'
    canvas.before:
        Color:
            rgba: app.t['bg']
        Rectangle:
            pos: self.pos
            size: self.size
    TopBar:
    ScrollView:
        do_scroll_x: False
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: self.minimum_height
            padding: dp(16)
            spacing: dp(16)
            DarkCard:
                SectionLabel:
                    text: 'PACKAGE FILE'
                SecInput:
                    id: package_path
                    hint_text: 'Tap Browse to select a package...'
                    readonly: True
                BoxLayout:
                    spacing: dp(8)
                    size_hint_y: None
                    height: dp(44)
                    SecButton:
                        text: 'Browse'
                        on_release: app.open_filechooser()
                    AppButton:
                        text: 'Analyze'
                        on_release: app.analyze_package()
            DarkCard:
                SectionLabel:
                    text: 'PACKAGE INFO'
                Label:
                    id: package_info
                    text: 'No package selected'
                    font_size: sp(13)
                    color: app.t['text_secondary']
                    size_hint_y: None
                    height: dp(90)
                    text_size: self.size
                    halign: 'left'
                    valign: 'top'
                    markup: True
            DarkCard:
                SectionLabel:
                    text: 'GENERATED default.nix'
                BoxLayout:
                    spacing: dp(8)
                    size_hint_y: None
                    height: dp(44)
                    SecButton:
                        text: 'Copy'
                        on_release: app.copy_nix()
                    SecButton:
                        text: 'Save'
                        on_release: app.save_nix()
                MonoInput:
                    id: nix_output
                    text: ''
            DarkCard:
                SectionLabel:
                    text: 'DEPENDENCIES'
                MonoInput:
                    id: deps_output
                    text: ''
                    height: dp(100)
            BoxLayout:
                size_hint_y: None
                height: dp(36)
                Label:
                    id: status_bar
                    text: 'Ready'
                    font_size: sp(12)
                    color: app.t['text_secondary']
                    text_size: self.size
                    halign: 'left'
                    valign: 'middle'
"""


class MainLayout(BoxLayout):
    pass


class FileChooserPopup(ModalView):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.size_hint = (0.95, 0.85)

        layout = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        layout.add_widget(Label(
            text="Select a package file",
            font_size=sp(16), bold=True,
            size_hint_y=None, height=dp(36),
            color=app_ref.t["text_primary"],
        ))

        from kivy.uix.filebrowser import FileBrowser
        default_path = "/sdcard/Download"
        if not os.path.isdir(default_path):
            default_path = str(Path.home())

        self.browser = FileBrowser(path=default_path, multiselect=False)
        layout.add_widget(self.browser)

        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel = Button(
            text="Cancel", font_size=sp(14),
            background_color=(0, 0, 0, 0),
            color=app_ref.t["text_secondary"],
        )
        cancel.bind(on_release=lambda _: self.dismiss())
        btn_row.add_widget(cancel)
        select = Button(
            text="Select", font_size=sp(14), bold=True,
            background_color=(0, 0, 0, 0),
            color=app_ref.t["accent"],
        )
        select.bind(on_release=lambda _: self._select())
        btn_row.add_widget(select)
        layout.add_widget(btn_row)
        self.add_widget(layout)

    def _select(self):
        if self.browser.selection:
            path = self.browser.selection[0]
            if os.path.isfile(path):
                self.app_ref.set_package_path(path)
        self.dismiss()


class app2nixApp(App):
    dark_mode = BooleanProperty(True)
    t = DictProperty({})
    theme_icon = StringProperty("\u2600\ufe0f")
    _current_file = StringProperty("")
    _nix_content = StringProperty("")

    def build(self):
        self.title = "app2nix"
        self._apply_theme()
        Window.clearcolor = self.t["bg"]
        return Builder.load_string(KV)

    def _apply_theme(self):
        self.t = (DARK if self.dark_mode else LIGHT).copy()
        self.theme_icon = "\u2600\ufe0f" if self.dark_mode else "\U0001f319"
        Window.clearcolor = self.t["bg"]

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme()

    def open_filechooser(self):
        FileChooserPopup(self).open()

    def set_package_path(self, path: str):
        self._current_file = path
        self.root.ids.package_path.text = path
        self.root.ids.status_bar.text = f"Selected: {os.path.basename(path)}"

    # Formats requiring subprocess (dpkg-deb, rpm, unsquashfs, patchelf)
    # cannot run on Android. Only pure-Python formats are supported.
    _ANDROID_UNSUPPORTED = {"deb", "rpm", "appimage", "flatpak", "snap", "7z"}

    def analyze_package(self):
        path = self._current_file
        if not path:
            self.root.ids.status_bar.text = "No file selected"
            return
        fmt = detect_format(path)
        if not fmt:
            self.root.ids.status_bar.text = f"Unsupported: {Path(path).suffix}"
            return
        # Check Android compatibility
        if hasattr(sys, "getandroidapilevel") and fmt in self._ANDROID_UNSUPPORTED:
            self.root.ids.status_bar.text = f"{fmt} not available on Android (needs subprocess)"
            return
        self.root.ids.status_bar.text = f"Analyzing {os.path.basename(path)}..."
        threading.Thread(target=self._do_analyze, args=(path,), daemon=True).start()

    def _do_analyze(self, path: str):
        try:
            analyzer = UniversalAnalyzer()
            info = analyzer.analyze(path)

            resolver = DependencyResolver()
            resolved, unresolved = resolver.resolve_all(info.dependencies)

            generator = NixGenerator()
            result = generator.generate_default_nix(info, resolved_deps=resolved)

            deps_lines = []
            for lib in info.dependencies:
                deps_lines.append(f"  {lib}")
            if unresolved:
                deps_lines.append(f"  --- unresolved: {len(unresolved)} ---")
                for u in unresolved[:20]:
                    deps_lines.append(f"  ? {u}")
            deps_str = "\n".join(deps_lines) if deps_lines else "  (none)"

            self._analysis = (info, result)
            self._nix_content = result.nix_content
            self._update_ui(info, result, deps_str)
        except Exception as exc:
            self._show_error(str(exc))

    @mainthread
    def _update_ui(self, info, result, deps_str: str):
        self.root.ids.package_info.text = (
            f"[b]Name:[/b] {info.name}\n"
            f"[b]Version:[/b] {info.version}\n"
            f"[b]Format:[/b] {info.format}\n"
            f"[b]Arch:[/b] {info.architecture}\n"
            f"[b]Deps:[/b] {len(info.dependencies)} found"
        )
        self.root.ids.nix_output.text = result.nix_content
        self.root.ids.deps_output.text = deps_str
        status = f"OK: {info.name} v{info.version}"
        if result.unresolved_deps:
            status += f" ({len(result.unresolved_deps)} unresolved)"
        self.root.ids.status_bar.text = status

    @mainthread
    def _show_error(self, msg: str):
        self.root.ids.status_bar.text = f"Error: {msg}"
        self.root.ids.nix_output.text = f"# Error: {msg}"

    def copy_nix(self):
        content = self._nix_content or self.root.ids.nix_output.text
        if content:
            Clipboard.copy(content)
            self.root.ids.status_bar.text = "Copied to clipboard"

    def save_nix(self):
        content = self._nix_content or self.root.ids.nix_output.text
        if not content:
            self.root.ids.status_bar.text = "Nothing to save"
            return
        try:
            from android.storage import primary_external_storage_path
            save_dir = os.path.join(primary_external_storage_path(), "Download")
        except Exception:
            save_dir = str(Path.home())
        try:
            save_path = os.path.join(save_dir, "default.nix")
            with open(save_path, "w") as f:
                f.write(content)
            self.root.ids.status_bar.text = f"Saved: {save_path}"
        except Exception as exc:
            self.root.ids.status_bar.text = f"Save failed: {exc}"


if __name__ == "__main__":
    app2nixApp().run()
