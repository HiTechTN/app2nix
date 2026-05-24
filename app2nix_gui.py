#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QActionGroup, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).parent / "src"))
from app2nix.core.analyzer import UniversalAnalyzer
from app2nix.core.resolver import DependencyResolver, DEP_MAP
from lib import i18n
from lib import theme as thm

SUPPORTED_FORMATS = [".deb", ".rpm", ".AppImage", ".appimage", ".tar.gz", ".tgz", ".tar", ".flatpak", ".snap"]
ARCH_MAP = {
    "amd64": "x86_64-linux", "i386": "i686-linux", "i686": "i686-linux",
    "arm64": "aarch64-linux", "armhf": "armv7l-linux", "arm": "armv7l-linux",
    "unknown": "x86_64-linux", "x86_64": "x86_64-linux",
}

def map_arch(arch: str) -> str:
    return ARCH_MAP.get(arch.lower(), arch)

def get_format(filename: str) -> str | None:
    name = filename.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        return ".tar.gz"
    ext = Path(name).suffix
    return ext if ext in SUPPORTED_FORMATS else None

def build_nix_expression(pkg_name: str, pkg_version: str, pkg_arch: str, fmt: str, deps_lines: str) -> str:
    if fmt == "deb":
        extract = ('deb_file=$(find $src -name "*.deb" -o -name "*.ipk" 2>/dev/null | head -1); '
                   'if [ -n "$deb_file" ]; then dpkg-deb -x "$deb_file" $out; '
                   'else echo "ERROR: no .deb file found in $src"; exit 1; fi')
        native = ["dpkg", "autoPatchelfHook"]
    elif fmt in ("AppImage", "appimage"):
        extract = ('appimage=$(find $src -name "*.AppImage" -o -name "*.appimage" 2>/dev/null | head -1); '
                   'if [ -n "$appimage" ]; then chmod +x "$appimage"; "$appimage" --appimage-extract 2>/dev/null; '
                   'if [ -d squashfs-root ]; then cp -r squashfs-root/* $out/; rm -rf squashfs-root; '
                   'else echo "ERROR: appimage-extract failed"; exit 1; fi; '
                   'else echo "ERROR: no AppImage file found in $src"; exit 1; fi')
        native = ["autoPatchelfHook"]
    else:
        extract = ('pkg_file=$(find $src -type f ! -name "*.nix" ! -name "*.sh" 2>/dev/null | head -1); '
                   'if [ -n "$pkg_file" ]; then mkdir -p $out/bin && cp "$pkg_file" $out/bin/; '
                   'else echo "ERROR: no package file found in $src"; exit 1; fi')
        native = ["autoPatchelfHook"]

    native_inputs = "\n".join(f"    pkgs.{p}" for p in native)
    lines = [
        "{ pkgs ? import <nixpkgs> {} }:",
        "",
        "let",
        f'  pname = "{pkg_name}";',
        f'  version = "{pkg_version}";',
        "in pkgs.stdenv.mkDerivation {",
        "  inherit pname version;",
        "",
        "  src = ./.;",
        "",
        "  nativeBuildInputs = with pkgs; [",
        native_inputs,
        "  ];",
        "",
    ]
    deps_extra = "    pkgs.stdenv.cc.cc.lib\n" if "stdenv.cc.cc.lib" not in deps_lines else ""
    all_deps = deps_extra + deps_lines
    if all_deps.strip():
        lines.append("  buildInputs = with pkgs; [")
        lines.append(all_deps)
        lines.append("  ];")
        lines.append("")

    lines.extend([
        '  phases = [ "unpackPhase" "installPhase" "fixupPhase" ];',
        "",
        '  unpackPhase = "true";',
        "",
        "  installPhase = ''",
        "    mkdir -p $out",
        f"    {extract}",
        "",
        "    mkdir -p $out/bin",
        '    find $out/usr $out/opt -type f -executable 2>/dev/null | while read f; do',
        '      case "$f" in *.so.*|*.so) ;; *) ln -sf "$f" "$out/bin/$(basename "$f")" 2>/dev/null ;; esac',
        '    done',
        "",
        '    if [ -d "$out/usr/share" ]; then',
        "      mkdir -p $out/share",
        '      cp -r $out/usr/share/* $out/share/ 2>/dev/null || true',
        "    fi",
        "  '';",
        "",
        "  preFixup = ''",
        "    autoPatchelf $out",
        "  '';",
        "",
        '  meta = with pkgs.lib; {',
        '    description = "' + pkg_name + ' package converted for NixOS";',
        f'    platforms = [ "{pkg_arch}" ];',
        "    license = licenses.unfree;",
        "  };",
        "}",
    ])
    return "\n".join(lines)


def build_stylesheet(t: dict) -> str:
    return f"""
QMainWindow {{ background-color: {t['bg']}; }}
QLineEdit {{ padding: 10px 14px; border: 1px solid {t['input_border']}; border-radius: 8px; font-size: 14px; background: {t['input_bg']}; color: {t['text_primary']}; }}
QLineEdit:focus {{ border-color: {t['input_focus']}; }}
QLineEdit::placeholder {{ color: {t['text_muted']}; }}
QProgressBar {{ border-radius: 6px; height: 6px; text-align: center; background: {t['progress_bg']}; border: none; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {t['accent']},stop:1 #8b5cf6); border-radius: 6px; }}
QStatusBar {{ background: {t['status_bg']}; color: {t['status_text']}; border: none; padding: 2px 12px; font-size: 12px; }}
QTabWidget::pane {{ background: {t['card_bg']}; border-radius: 0 0 12px 12px; border: 1px solid {t['card_border']}; border-top: none; padding: 0; }}
QTabBar::tab {{ background: {t['tab_bg']}; color: {t['tab_text']}; padding: 12px 24px; font-size: 13px; font-weight: bold; border: 1px solid {t['card_border']}; border-bottom: none; border-radius: 8px 8px 0 0; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {t['card_bg']}; color: {t['tab_selected']}; border-bottom: 2px solid {t['tab_selected']}; }}
QTabBar::tab:hover {{ color: {t['text_primary']}; }}
QMenuBar {{ background: transparent; border: none; color: {t['header_text']}; }}
QMenuBar::item:selected {{ background: rgba(255,255,255,0.1); border-radius: 4px; }}
QMenu {{ background: {t['menu_bg']}; color: {t['menu_text']}; border: 1px solid {t['card_border']}; border-radius: 8px; }}
QMenu::item:selected {{ background: {t['menu_hover']}; }}
QWidget#header {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {t['header_start']},stop:1 {t['header_end']}); }}
QWidget#input_card {{ background: {t['card_bg']}; border-radius: 12px; border: 1px solid {t['card_border']}; }}
QWidget#info_card {{ background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 10px; }}
QWidget#libs_card {{ background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 10px; }}
QWidget#separator {{ background: {t['separator']}; max-height: 1px; min-height: 1px; }}
"""


class App2NixWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.current_result = None
        self._tr_items: list[tuple] = []
        self._tab_widget = None
        self._status_bar = None
        self._header_subtitle = None
        self._menu_actions: list[tuple] = []

        self._setup_ui()
        self._setup_menu()
        self._apply_theme()
        self._retranslate_ui()
        self.setMinimumSize(1000, 700)

    # ---------- theme / i18n ----------

    def _apply_theme(self):
        self.setStyleSheet(build_stylesheet(thm.get()))
        ct = thm.get()
        header = self.findChild(QWidget, "header")
        if header:
            header.setStyleSheet(
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ct['header_start']},stop:1 {ct['header_end']});"
            )
        if self._header_subtitle:
            self._header_subtitle.setStyleSheet(f"color: {ct['header_subtitle']}; font-size: 14px; background: transparent;")
        for area in ("result_tab", "nix_tab", "install_tab"):
            t = getattr(self, area, None)
            if t:
                t.setStyleSheet(f"background: {ct['card_bg']};")

    def _retranslate_ui(self):
        self.setWindowTitle(i18n.tr("window.title"))
        for w, key in self._tr_items:
            try:
                w.setText(i18n.tr(key))
            except Exception:
                pass
        for action, key in self._menu_actions:
            try:
                action.setText(i18n.tr(key))
            except Exception:
                pass
        if self._file_menu:
            self._file_menu.setTitle(i18n.tr("menu.file"))
        if self._edit_menu:
            self._edit_menu.setTitle(i18n.tr("menu.edit"))
        if self._lang_menu:
            self._lang_menu.setTitle(i18n.tr("menu.language"))
        if self._theme_menu:
            self._theme_menu.setTitle(i18n.tr("menu.theme"))
        if self._help_menu:
            self._help_menu.setTitle(i18n.tr("menu.help"))
        if self._tab_widget:
            self._tab_widget.setTabText(0, i18n.tr("tab.results"))
            self._tab_widget.setTabText(1, i18n.tr("tab.nix"))
            self._tab_widget.setTabText(2, i18n.tr("tab.install"))
        if self.file_path:
            self.file_path.setPlaceholderText(i18n.tr("file.placeholder"))
        if self.url_input:
            self.url_input.setPlaceholderText(i18n.tr("url.placeholder"))
        if self._header_subtitle:
            self._header_subtitle.setText(i18n.tr("app.subtitle"))
        if self._status_bar:
            self._status_bar.showMessage(i18n.tr("status.ready"))

    def _change_language(self, code: str):
        if i18n.load(code):
            self._retranslate_ui()
            QApplication.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft if i18n.is_rtl() else Qt.LayoutDirection.LeftToRight
            )

    def _change_theme(self, name: str):
        thm.set(name)
        self._apply_theme()

    # ---------- menu ----------

    def _setup_menu(self):
        mb = self.menuBar()

        self._file_menu = mb.addMenu("")
        self._edit_menu = mb.addMenu("")
        self._lang_menu = mb.addMenu("")
        self._theme_menu = mb.addMenu("")
        self._help_menu = mb.addMenu("")

        open_a = QAction("", self)
        open_a.setShortcut("Ctrl+O")
        open_a.triggered.connect(self._select_file)
        self._file_menu.addAction(open_a)
        self._menu_actions.append((open_a, "menu.open"))
        self._file_menu.addSeparator()
        exit_a = QAction("", self)
        exit_a.setShortcut("Ctrl+Q")
        exit_a.triggered.connect(self.close)
        self._file_menu.addAction(exit_a)
        self._menu_actions.append((exit_a, "menu.exit"))

        copy_a = QAction("", self)
        copy_a.setShortcut("Ctrl+C")
        copy_a.triggered.connect(self._copy_nix)
        self._edit_menu.addAction(copy_a)
        self._menu_actions.append((copy_a, "menu.copy"))

        lg = QActionGroup(self)
        lg.setExclusive(True)
        for code, name in i18n.available():
            a = QAction(name, self, checkable=True)
            a.setChecked(code == i18n.lang())
            a.triggered.connect(lambda checked, c=code: self._change_language(c))
            self._lang_menu.addAction(a)

        tg = QActionGroup(self)
        tg.setExclusive(True)
        for tname in ("light", "dark"):
            a = QAction(tname.capitalize(), self, checkable=True)
            a.setChecked(tname == thm.name())
            a.triggered.connect(lambda checked, n=tname: self._change_theme(n))
            self._theme_menu.addAction(a)

        about_a = QAction("", self)
        about_a.triggered.connect(self._show_about)
        self._help_menu.addAction(about_a)
        self._menu_actions.append((about_a, "menu.about"))

        for m in (self._file_menu, self._edit_menu, self._lang_menu, self._theme_menu, self._help_menu):
            mb.addMenu(m)

    # ---------- main UI ----------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        ml = QVBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # header
        header = QWidget()
        header.setObjectName("header")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 16)

        title_row = QHBoxLayout()
        logo = QLabel("📦")
        logo.setStyleSheet("font-size: 32px; background: transparent;")
        title_text = QLabel("app2nix")
        title_text.setStyleSheet("font-size: 26px; font-weight: bold; color: white; background: transparent;")
        title_row.addWidget(logo)
        title_row.addWidget(title_text)
        title_row.addStretch()

        self._header_subtitle = QLabel("")
        hl.addLayout(title_row)
        hl.addWidget(self._header_subtitle)
        ml.addWidget(header)

        # content area
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(16)

        # input card
        card = QWidget()
        card.setObjectName("input_card")
        cardl = QVBoxLayout(card)
        cardl.setContentsMargins(20, 16, 20, 16)
        cardl.setSpacing(12)

        input_label = QLabel("")
        input_label.setStyleSheet("font-size: 15px; font-weight: bold; background: transparent;")
        self._tr_items.append((input_label, "package.input"))

        self.file_path = QLineEdit()
        browse_btn = QPushButton("")
        browse_btn.clicked.connect(self._select_file)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(
            "QPushButton { background: #f0f2f5; color: #374151; padding: 10px 18px; border-radius: 8px; font-size: 13px; font-weight: bold; border: 1px solid #d1d5db; }"
            "QPushButton:hover { background: #e5e7eb; border-color: #9ca3af; }"
        )
        self._tr_items.append((browse_btn, "file.browse"))

        fr = QHBoxLayout()
        fr.addWidget(self.file_path, 1)
        fr.addWidget(browse_btn)
        cardl.addWidget(input_label)
        cardl.addLayout(fr)

        sep1 = QWidget()
        sep1.setObjectName("separator")
        sep1.setFixedHeight(1)
        cardl.addWidget(sep1)

        urlr = QHBoxLayout()
        url_icon = QLabel("🔗")
        url_icon.setStyleSheet("background: transparent; font-size: 16px;")
        self.url_input = QLineEdit()
        urlr.addWidget(url_icon)
        urlr.addWidget(self.url_input, 1)
        cardl.addLayout(urlr)

        sep2 = QWidget()
        sep2.setObjectName("separator")
        sep2.setFixedHeight(1)
        cardl.addWidget(sep2)

        br = QHBoxLayout()
        self.analyze_btn = QPushButton("")
        self.analyze_btn.setDefault(True)
        self.analyze_btn.clicked.connect(self._analyze)
        self.analyze_btn.setMinimumHeight(44)
        self.analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.analyze_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b82f6,stop:1 #2563eb); color: white; font-weight: bold; font-size: 15px; border-radius: 10px; padding: 0 32px; }"
            "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2563eb,stop:1 #1d4ed8); }"
            "QPushButton:disabled { background: #9ca3af; }"
        )
        self._tr_items.append((self.analyze_btn, "analyze.btn"))

        self.clear_btn = QPushButton("")
        self.clear_btn.clicked.connect(self._clear)
        self.clear_btn.setMinimumHeight(44)
        self.clear_btn.setStyleSheet(
            "QPushButton { background: #f0f2f5; color: #374151; padding: 0 20px; border-radius: 10px; font-size: 14px; font-weight: bold; border: 1px solid #d1d5db; }"
            "QPushButton:hover { background: #e5e7eb; }"
        )
        self._tr_items.append((self.clear_btn, "clear.btn"))

        br.addStretch()
        br.addWidget(self.analyze_btn)
        br.addWidget(self.clear_btn)
        cardl.addLayout(br)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximum(0)
        self.progress.setFixedHeight(6)
        cardl.addWidget(self.progress)

        cl.addWidget(card)

        # tabs
        self._tab_widget = QTabWidget()
        self.result_tab = QWidget()
        self.nix_tab = QWidget()
        self.install_tab = QWidget()
        self._tab_widget.addTab(self.result_tab, "")
        self._tab_widget.addTab(self.nix_tab, "")
        self._tab_widget.addTab(self.install_tab, "")
        cl.addWidget(self._tab_widget, 1)

        ml.addWidget(content, 1)

        self._setup_result_tab()
        self._setup_nix_tab()
        self._setup_install_tab()

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    # ---------- result tab ----------

    def _setup_result_tab(self):
        layout = QVBoxLayout(self.result_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        info_card = QWidget()
        info_card.setObjectName("info_card")
        il = QVBoxLayout(info_card)
        il.setContentsMargins(16, 16, 16, 12)

        grid = QHBoxLayout()
        grid.setSpacing(24)

        def mk_item(tkey, aname):
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel("")
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px; text-transform: uppercase; font-weight: bold; background: transparent;")
            self._tr_items.append((lbl, tkey))
            w = QLabel("-")
            w.setStyleSheet("font-size: 16px; font-weight: bold; background: transparent;")
            setattr(self, aname, w)
            col.addWidget(lbl)
            col.addWidget(w)
            return col

        grid.addLayout(mk_item("info.name", "lbl_name"))
        grid.addLayout(mk_item("info.version", "lbl_version"))
        grid.addLayout(mk_item("info.arch", "lbl_arch"))
        grid.addLayout(mk_item("info.format", "lbl_format"))
        grid.addLayout(mk_item("info.libs", "lbl_libs_count"))
        grid.addLayout(mk_item("info.nixpkgs", "lbl_nix_count"))
        il.addLayout(grid)
        layout.addWidget(info_card)

        libs_card = QWidget()
        libs_card.setObjectName("libs_card")
        lcl = QVBoxLayout(libs_card)
        lcl.setContentsMargins(16, 14, 16, 14)

        lh = QLabel("")
        self._tr_items.append((lh, "libs.header"))
        lh.setStyleSheet("font-size: 14px; font-weight: bold; background: transparent;")
        lcl.addWidget(lh)

        self.libs_text = QTextEdit()
        self.libs_text.setReadOnly(True)
        self.libs_text.setFont(QFont("monospace", 10))
        self.libs_text.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none; border-radius: 8px; padding: 8px;")
        lcl.addWidget(self.libs_text, 1)
        layout.addWidget(libs_card, 1)

        self.install_btn = QPushButton("")
        self.install_btn.setMinimumHeight(48)
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1a6b3c,stop:1 #15803d); color: white; font-weight: bold; font-size: 15px; border-radius: 10px; }"
            "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #15803d,stop:1 #166534); }"
            "QPushButton:disabled { background: #9ca3af; }"
        )
        self.install_btn.clicked.connect(self._install_to_system)
        self.install_btn.setVisible(False)
        self._tr_items.append((self.install_btn, "install.btn"))
        layout.addWidget(self.install_btn)

    # ---------- nix tab ----------

    def _setup_nix_tab(self):
        layout = QVBoxLayout(self.nix_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        tb = QHBoxLayout()
        copy_btn = QPushButton("")
        copy_btn.clicked.connect(self._copy_nix)
        copy_btn.setStyleSheet("QPushButton { background: #3b82f6; color: white; padding: 8px 18px; border-radius: 8px; font-weight: bold; } QPushButton:hover { background: #2563eb; }")
        self._tr_items.append((copy_btn, "nix.copy"))
        save_btn = QPushButton("")
        save_btn.clicked.connect(self._save_nix)
        save_btn.setStyleSheet("QPushButton { background: #f0f2f5; color: #374151; padding: 8px 18px; border-radius: 8px; font-weight: bold; border: 1px solid #d1d5db; } QPushButton:hover { background: #e5e7eb; }")
        self._tr_items.append((save_btn, "nix.save"))
        tb.addWidget(copy_btn)
        tb.addWidget(save_btn)
        tb.addStretch()
        layout.addLayout(tb)

        self.nix_output = QTextEdit()
        self.nix_output.setReadOnly(True)
        self.nix_output.setFont(QFont("monospace", 11))
        self.nix_output.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none; border-radius: 10px; padding: 16px;")
        layout.addWidget(self.nix_output, 1)

    # ---------- install tab ----------

    def _setup_install_tab(self):
        layout = QVBoxLayout(self.install_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        br = QHBoxLayout()
        copy_btn = QPushButton("")
        copy_btn.clicked.connect(self._copy_install_guide)
        copy_btn.setStyleSheet("QPushButton { background: #3b82f6; color: white; padding: 8px 18px; border-radius: 8px; font-weight: bold; } QPushButton:hover { background: #2563eb; }")
        self._tr_items.append((copy_btn, "install.copy"))
        save_btn = QPushButton("")
        save_btn.clicked.connect(self._save_install_script)
        save_btn.setStyleSheet("QPushButton { background: #f0f2f5; color: #374151; padding: 8px 18px; border-radius: 8px; font-weight: bold; border: 1px solid #d1d5db; } QPushButton:hover { background: #e5e7eb; }")
        self._tr_items.append((save_btn, "install.save"))
        self.setup_dir_btn = QPushButton("")
        self.setup_dir_btn.clicked.connect(self._auto_setup_package_dir)
        self.setup_dir_btn.setStyleSheet(
            "QPushButton { background: #1a6b3c; color: white; padding: 8px 18px; border-radius: 8px; font-weight: bold; }"
            "QPushButton:hover { background: #15803d; }"
            "QPushButton:disabled { background: #9ca3af; }"
        )
        self.setup_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setup_dir_btn.setVisible(False)
        self._tr_items.append((self.setup_dir_btn, "install.setup"))

        br.addWidget(copy_btn)
        br.addWidget(save_btn)
        br.addStretch()
        br.addWidget(self.setup_dir_btn)
        layout.addLayout(br)

        self.install_output = QTextEdit()
        self.install_output.setReadOnly(True)
        self.install_output.setStyleSheet("font-size: 14px; padding: 16px; border: none; border-radius: 10px;")
        layout.addWidget(self.install_output, 1)

    # ---------- actions ----------

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("menu.open"), "",
            i18n.tr("package_files")
        )
        if path:
            self.file_path.setText(path)
            self.current_file = path

    def _analyze(self):
        file_path = self.file_path.text().strip()
        url = self.url_input.text().strip()

        if not file_path and not url:
            QMessageBox.warning(self, i18n.tr("error.no_input"), i18n.tr("error.select_file"))
            return

        if url:
            self._status_bar.showMessage(i18n.tr("status.downloading"))
            self.progress.setVisible(True)
            self.analyze_btn.setEnabled(False)
            QApplication.processEvents()
            try:
                dest = f"/tmp/app2nix_download_{abs(hash(url))}"
                urllib.request.urlretrieve(url, dest)
                file_path = dest
                self.file_path.setText(file_path)
                self.current_file = file_path
            except Exception as e:
                self.progress.setVisible(False)
                self.analyze_btn.setEnabled(True)
                QMessageBox.critical(self, i18n.tr("error.download"), str(e))
                return

        if not os.path.exists(file_path):
            QMessageBox.critical(self, i18n.tr("error.not_found"), f"{i18n.tr('error.not_found')}: {file_path}")
            return

        fmt = get_format(file_path)
        if not fmt:
            QMessageBox.warning(self, i18n.tr("error.unsupported"),
                                f"{i18n.tr('error.unsupported')}: {', '.join(SUPPORTED_FORMATS)}")
            return

        self._status_bar.showMessage(i18n.tr("status.analyzing"))
        self.progress.setVisible(True)
        self.analyze_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            analyzer = UniversalAnalyzer()
            info = analyzer.analyze(file_path)

            resolver = DependencyResolver(Path("/tmp/app2nix_resolver.db"))
            nix_deps, unresolved = resolver.resolve_all(info.dependencies)
            pkg_name = info.name
            pkg_version = info.version
            pkg_arch = info.architecture
            fmt_name = info.format

            self.current_result = {
                "name": pkg_name, "version": pkg_version,
                "architecture": pkg_arch, "format": fmt_name,
                "libraries": info.dependencies,
                "nix_dependencies": nix_deps,
            }

            self.lbl_name.setText(pkg_name)
            self.lbl_version.setText(pkg_version)
            self.lbl_arch.setText(map_arch(pkg_arch))
            self.lbl_format.setText(fmt_name)
            self.lbl_libs_count.setText(str(len(info.dependencies)))
            self.lbl_nix_count.setText(str(len(nix_deps)))

            self.libs_text.clear()
            for lib in sorted(info.dependencies):
                self.libs_text.append(lib)

            pa = map_arch(pkg_arch)
            dl = "\n".join(f"    pkgs.{dep}" for dep in nix_deps)
            self.nix_output.setPlainText(build_nix_expression(pkg_name, pkg_version, pa, fmt_name, dl))

            install_guide = (
                f'<div style="font-family: system-ui, sans-serif; line-height: 1.8;">'
                f'<h2 style="color: #2d4f8c; border-bottom: 3px solid #2d4f8c; padding-bottom: 8px; margin-top: 0;">📦 {i18n.tr("install.guide.title")}: {pkg_name} v{pkg_version}</h2>'
                f'<table style="width:100%;border-collapse:collapse;margin:12px 0;background:white;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);">'
                f'<tr><td style="padding:8px 16px;color:#555;font-weight:bold;width:100px;">Format</td>'
                f'<td style="padding:8px 16px;"><span style="background:#e3f2fd;color:#1565c0;padding:2px 10px;border-radius:12px;font-size:13px;">{fmt_name}</span></td></tr>'
                f'<tr><td style="padding:8px 16px;color:#555;font-weight:bold;">Arch</td>'
                f'<td style="padding:8px 16px;"><span style="background:#f3e5f5;color:#7b1fa2;padding:2px 10px;border-radius:12px;font-size:13px;">{map_arch(pkg_arch)}</span></td></tr>'
                f'<tr><td style="padding:8px 16px;color:#555;font-weight:bold;">Deps</td>'
                f'<td style="padding:8px 16px;"><span style="background:#e8f5e9;color:#2e7d32;padding:2px 10px;border-radius:12px;font-size:13px;">{len(nix_deps)} nixpkgs</span></td></tr>'
                f'</table>'
                f'<div style="background:#e3f2fd;border-left:4px solid #1565c0;padding:10px 14px;margin:12px 0;border-radius:4px;">'
                f'<strong style="color:#1565c0;">🔧 {i18n.tr("install.step1")}</strong></div>'
                f'<pre style="background:#1e1e2e;color:#cdd6f4;padding:12px 16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.6;">'
                f'mkdir -p ~/nix-packages/{pkg_name}\ncd ~/nix-packages/{pkg_name}</pre>'
                f'<div style="background:#fff3e0;border-left:4px solid #e65100;padding:10px 14px;margin:16px 0 12px;border-radius:4px;">'
                f'<strong style="color:#e65100;">📄 {i18n.tr("install.step2")}</strong></div>'
                f'<div style="background:#e8f5e9;border-left:4px solid #2e7d32;padding:10px 14px;margin:16px 0 12px;border-radius:4px;">'
                f'<strong style="color:#2e7d32;">🚀 {i18n.tr("install.step3")}</strong></div>'
                f'<div style="margin:8px 0;"><span style="background:#1a6b3c;color:white;padding:3px 12px;border-radius:12px;font-size:12px;font-weight:bold;">{i18n.tr("install.user")}</span></div>'
                f'<pre style="background:#1e1e2e;color:#cdd6f4;padding:12px 16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.6;">'
                f'NIXPKGS_ALLOW_UNFREE=1 nix-env -i -f default.nix</pre>'
                f'<div style="margin:12px 0 8px;"><span style="background:#7b1fa2;color:white;padding:3px 12px;border-radius:12px;font-size:12px;font-weight:bold;">{i18n.tr("install.system")}</span></div>'
                f'<pre style="background:#1e1e2e;color:#cdd6f4;padding:12px 16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.6;">'
                f'# Add to /etc/nixos/configuration.nix:\n&#35; environment.systemPackages = with pkgs; [\n&#35;   (callPackage ~/nix-packages/{pkg_name} {{}})\n&#35; ];\n# Then run:\nsudo nixos-rebuild switch</pre>'
                f'<div style="margin-top:16px;padding:10px;background:#fff8e1;border:1px solid #ffe082;border-radius:8px;text-align:center;color:#795548;">'
                f'💡 <strong>{i18n.tr("install.tip")}</strong></div></div>'
            )
            self.install_output.setHtml(install_guide)
            self.setup_dir_btn.setVisible(True)
            self.setup_dir_btn.setEnabled(True)
            self.install_btn.setVisible(True)
            self._status_bar.showMessage(f"{i18n.tr('status.complete')}: {pkg_name} v{pkg_version}")
        except Exception as e:
            self._status_bar.showMessage(i18n.tr("status.failed"))
            QMessageBox.critical(self, i18n.tr("error.analysis"), str(e))
        finally:
            self.progress.setVisible(False)
            self.analyze_btn.setEnabled(True)

    def _install_to_system(self):
        if not self.current_result or not self.current_file:
            return
        pkg_name = self.current_result["name"]
        pkg_version = self.current_result["version"]
        pkg_dir = Path.home() / "nix-packages" / pkg_name
        nix_expr = self.nix_output.toPlainText()

        self._status_bar.showMessage(f"{i18n.tr('status.installing')} {pkg_name}...")
        self.progress.setVisible(True)
        self.install_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            pkg_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.current_file, pkg_dir / Path(self.current_file).name)
            (pkg_dir / "default.nix").write_text(nix_expr)

            env = os.environ.copy()
            env["NIXPKGS_ALLOW_UNFREE"] = "1"
            result = subprocess.run(
                ["nix-build", "default.nix"], cwd=str(pkg_dir),
                capture_output=True, text=True, timeout=600, env=env,
            )
            if result.returncode != 0:
                raise RuntimeError(f"{i18n.tr('error.build_failed')}:\n{result.stderr}")

            store_path = result.stdout.strip().split("\n")[-1].strip()
            if not store_path.startswith("/nix/store/"):
                raise RuntimeError(f"Unexpected nix-build output:\n{result.stdout}")

            bin_dir = Path(store_path) / "bin"
            share_dir = Path(store_path) / "share"
            apps_dir = Path.home() / ".local/share/applications"
            icons_dir = Path.home() / ".local/share/icons/hicolor/256x256/apps"
            apps_dir.mkdir(parents=True, exist_ok=True)
            icons_dir.mkdir(parents=True, exist_ok=True)

            executables = []
            if bin_dir.exists():
                for f in bin_dir.iterdir():
                    if f.is_file() and os.access(f, os.X_OK):
                        executables.append(f.name)
            if not executables:
                executables.append(pkg_name)

            for exe in executables:
                (apps_dir / f"{exe}.desktop").write_text(
                    f"[Desktop Entry]\nName={exe}\nComment={pkg_name} v{pkg_version} - installed by app2nix\n"
                    f"Exec={store_path}/bin/{exe}\nIcon={pkg_name.lower()}\nTerminal=false\n"
                    f"Type=Application\nCategories=Application;\nStartupNotify=true\n"
                )

            if share_dir.exists() and (share_dir / "icons").exists():
                for icon_file in (share_dir / "icons").rglob("*"):
                    if icon_file.is_file():
                        dest = icons_dir / f"{pkg_name.lower()}{icon_file.suffix}"
                        if dest.exists():
                            dest.unlink()
                        shutil.copy(icon_file, dest)

            self.progress.setVisible(False)
            choices = [f"{i18n.tr('open')} {exe}" for exe in executables] + [i18n.tr("close")]
            msg = QMessageBox(self)
            msg.setWindowTitle(i18n.tr("install.complete.title"))
            msg.setText(f"{pkg_name} v{pkg_version} {i18n.tr('install.complete.text')}")
            msg.setInformativeText(i18n.tr("install.complete.prompt"))
            for text in choices:
                msg.addButton(text, QMessageBox.ButtonRole.ActionRole)
            msg.exec()

            clicked = msg.clickedButton().text()
            if clicked != i18n.tr("close"):
                for exe in executables:
                    if clicked == f"{i18n.tr('open')} {exe}":
                        subprocess.Popen(
                            [str(Path(store_path) / "bin" / exe)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        break

            self._status_bar.showMessage(f"{pkg_name} {i18n.tr('status.installed')}")
        except Exception as e:
            self.progress.setVisible(False)
            QMessageBox.critical(self, i18n.tr("error.install"), str(e))
        finally:
            self.install_btn.setEnabled(True)

    def _clear(self):
        self.file_path.clear()
        self.url_input.clear()
        self.current_file = None
        self.current_result = None
        self.lbl_name.setText("-")
        self.lbl_version.setText("-")
        self.lbl_arch.setText("-")
        self.lbl_format.setText("-")
        self.lbl_libs_count.setText("-")
        self.lbl_nix_count.setText("-")
        self.libs_text.clear()
        self.nix_output.clear()
        self.install_output.clear()
        self.install_btn.setVisible(False)
        self._status_bar.showMessage(i18n.tr("status.ready"))

    def _copy_nix(self):
        t = self.nix_output.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status_bar.showMessage(i18n.tr("status.copied"))

    def _copy_install_guide(self):
        t = self.install_output.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status_bar.showMessage("Install guide copied to clipboard")

    def _save_nix(self):
        t = self.nix_output.toPlainText()
        if not t:
            return
        p, _ = QFileDialog.getSaveFileName(self, i18n.tr("save"), "default.nix",
                                          f"{i18n.tr('nix_files')};;{i18n.tr('all_files')}")
        if p:
            Path(p).write_text(t)
            self._status_bar.showMessage(f"{i18n.tr('save')}: {p}")

    def _save_install_script(self):
        t = self.install_output.toPlainText()
        if not t:
            return
        p, _ = QFileDialog.getSaveFileName(self, i18n.tr("save"), "install.sh",
                                          f"{i18n.tr('shell_files')};;{i18n.tr('all_files')}")
        if p:
            Path(p).write_text(t)
            self._status_bar.showMessage(f"{i18n.tr('save')}: {p}")

    def _auto_setup_package_dir(self):
        if not self.current_result or not self.current_file:
            return
        pn = self.current_result["name"]
        pd = Path.home() / "nix-packages" / pn
        pd.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.current_file, pd / Path(self.current_file).name)
        (pd / "default.nix").write_text(self.nix_output.toPlainText())
        self._status_bar.showMessage(f"{i18n.tr('status.setup_done')}: {pd}")
        QMessageBox.information(self, i18n.tr("setup.complete.title"),
            f"{i18n.tr('status.setup_done')}:\n{pd}\n\nPackage file copied\ndefault.nix saved\n\n"
            f"Run 'cd {pd} && NIXPKGS_ALLOW_UNFREE=1 nix-env -i -f default.nix' to install.")

    def _show_about(self):
        QMessageBox.about(self, i18n.tr("about.title"),
            f"<h3>app2nix {i18n.tr('about.version')}</h3>"
            f"<p>{i18n.tr('about.desc')}</p>"
            "<p>Convert .deb, .rpm, .AppImage, .tar.gz, .flatpak, .snap packages to NixOS expressions.</p>"
            "<p><a href='https://github.com/HiTechTN/app2nix'>github.com/HiTechTN/app2nix</a></p>")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("app2nix")
    window = App2NixWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
