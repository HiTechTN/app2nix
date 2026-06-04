"""Main window for the app2nix graphical interface."""

import os
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app2nix.gui.i18n import available as available_langs
from app2nix.gui.i18n import lang as current_lang
from app2nix.gui.i18n import load as load_lang
from app2nix.gui.i18n import tr
from app2nix.gui.theme import get as get_theme
from app2nix.gui.theme import set as set_theme

# Required keys for theme dictionaries (validated on every theme apply)
_REQUIRED_THEME_KEYS = {
    "header_start", "header_end", "bg", "header_text", "header_subtitle",
    "text_muted", "text_primary", "input_border", "input_bg", "input_focus",
    "accent", "accent_hover", "success", "success_hover",
    "btn_sec_bg", "btn_sec_text", "btn_sec_border", "btn_sec_hover",
    "separator", "card_bg", "card_border", "progress_bg",
    "tab_bg", "tab_text", "tab_selected", "tab_border",
    "help_card_bg", "help_card_border", "help_card_hover",
    "help_step_bg", "help_step_border",
}

# Formats supported by the core analyzer
SUPPORTED_EXTENSIONS = {
    ".deb", ".rpm", ".appimage", ".flatpak",
    ".snap", ".tar.gz", ".tgz", ".tar",
    ".tar.xz", ".tar.bz2", ".zip", ".7z",
}


# Well-known app name → category mapping (top 20 most popular)
_NAME_TO_CATEGORY: dict[str, str] = {
    "firefox": "Network;WebBrowser;",
    "chrome": "Network;WebBrowser;",
    "thunderbird": "Network;Email;",
    "gimp": "Graphics;2DGraphics;",
    "blender": "Graphics;3DGraphics;",
    "vlc": "AudioVideo;Player;",
    "mpv": "AudioVideo;Player;",
    "steam": "Game;",
    "discord": "Network;Chat;",
    "vscode": "Development;IDE;",
    "code": "Development;IDE;",
    "sublime": "Development;TextEditor;",
    "libreoffice": "Office;WordProcessor;",
    "filezilla": "Network;FileTransfer;",
    "keepassxc": "Utility;Security;",
    "signal": "Network;Chat;",
    "spotify": "AudioVideo;Audio;",
    "htop": "System;Monitor;",
    "intellij": "Development;IDE;",
    "docker": "Development;",
}

# Keyword heuristics for apps not in the dictionary
_KEYWORD_CATEGORIES: list[tuple[list[str], str]] = [
    (["browser", "firefox", "chrome", "chromium"], "Network;WebBrowser;"),
    (["editor", "notepad", "text"], "Development;TextEditor;"),
    (["player", "video", "media"], "AudioVideo;Player;"),
    (["audio", "music", "mixer"], "AudioVideo;Audio;"),
    (["chat", "messenger", "talk"], "Network;Chat;"),
    (["mail", "email", "inbox"], "Network;Email;"),
    (["game", "play"], "Game;"),
    (["ide", "code", "develop"], "Development;IDE;"),
    (["terminal", "console", "shell"], "System;TerminalEmulator;"),
    (["image", "photo", "picture", "view"], "Graphics;ImageViewer;"),
    (["design", "draw", "vector"], "Graphics;Design;"),
    (["download", "transfer", "torrent"], "Network;FileTransfer;"),
    (["security", "password", "vpn", "encrypt"], "Utility;Security;"),
    (["monitor", "process", "system"], "System;Monitor;"),
    (["office", "document", "spreadsheet", "presentation"], "Office;"),
]


def _guess_category(pkg_name: str) -> str:
    """Guess the freedesktop category from the package name."""
    lower = pkg_name.lower()
    if lower in _NAME_TO_CATEGORY:
        return _NAME_TO_CATEGORY[lower]
    for keywords, cat in _KEYWORD_CATEGORIES:
        if any(kw in lower for kw in keywords):
            return cat
    return "Utility;"


def _detect_format(path: str) -> str | None:
    """Return the extension key for a supported format, or None."""
    name = path.lower()
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.endswith(ext):
            return ext
    if name.endswith(".tgz"):
        return ".tar.gz"
    if name.endswith(".txz"):
        return ".tar.xz"
    if name.endswith(".tbz2"):
        return ".tar.bz2"
    ext = Path(name).suffix
    return ext if ext in SUPPORTED_EXTENSIONS else None


# ---------------------------------------------------------------------------
# Worker thread for analysis (prevents UI freeze)
# ---------------------------------------------------------------------------

class AnalyzeWorker(QThread):
    """Runs package analysis in a background thread."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, package_path: str, parent=None):
        super().__init__(parent)
        self._package_path = package_path

    def run(self):
        try:
            from app2nix.core.analyzer import UniversalAnalyzer

            analyzer = UniversalAnalyzer()
            info = analyzer.analyze(self._package_path)

            from app2nix.core.generator import NixGenerator

            generator = NixGenerator()
            result = generator.generate_default_nix(info)

            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Worker thread for installation (prevents UI freeze)
# ---------------------------------------------------------------------------

class InstallWorker(QThread):
    """Runs nix-build and install in a background thread."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, package_path: str, nix_content: str,
                 pkg_name: str, version: str,
                 system_install: bool = False,
                 sudo_password: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._package_path = package_path
        self._nix_content = nix_content
        self._pkg_name = pkg_name
        self._version = version
        self._system_install = system_install
        self._sudo_password = sudo_password

    def run(self):
        try:
            pkg_dir = Path.home() / "nix-packages" / self._pkg_name

            # Step 1: Create directory
            self.progress.emit(f"Creating {pkg_dir}...")
            pkg_dir.mkdir(parents=True, exist_ok=True)

            # Step 2: Copy package file
            src = Path(self._package_path)
            dest = pkg_dir / src.name
            if not dest.exists():
                self.progress.emit(f"Copying {src.name}...")
                shutil.copy2(src, dest)

            # Step 3: Write default.nix
            nix_file = pkg_dir / "default.nix"
            self.progress.emit("Writing default.nix...")
            nix_file.write_text(self._nix_content, encoding="utf-8")

            # Step 4: Check root permissions
            root_stat = Path("/").stat()
            if root_stat.st_mode & 0o002:  # world-writable
                if self._sudo_password:
                    self.progress.emit("Fixing root permissions (chmod 755 /)...")
                    self._run_cmd(
                        ["sudo", "-S", "chmod", "755", "/"],
                        stdin_data=self._sudo_password + "\n",
                    )
                else:
                    self.error.emit(
                        "Root directory is world-writable (777). Nix sandbox cannot work.\n"
                        "Please run: sudo chmod 755 /\n"
                        "Or enable 'System install' and enter your sudo password."
                    )
                    return

            # Step 5: Build with nix-build
            env = {"NIXPKGS_ALLOW_UNFREE": "1"}
            result_link = pkg_dir / "result"

            self.progress.emit("Building package...")
            self._run_cmd(
                ["nix-build", "-f", str(nix_file), "-o", str(result_link)],
                env=env,
            )

            # Step 6: Install into profile with nix profile install
            if self._system_install:
                self.progress.emit("Installing (system profile)...")
                self._run_cmd(
                    ["sudo", "-S", "nix", "profile", "install", str(result_link)],
                    stdin_data=self._sudo_password + "\n",
                    env=env,
                )
            else:
                self.progress.emit("Installing (user profile)...")
                self._run_cmd(
                    ["nix", "profile", "install", str(result_link)],
                    env=env,
                )

            try:
                self._install_desktop_files()
            except Exception as exc:
                self.progress.emit(f"Warning: desktop entry install failed: {exc}")

            self.finished.emit(
                f"{self._pkg_name} v{self._version} installed successfully!\n"
                f"Location: {pkg_dir}"
            )

        except subprocess.CalledProcessError as exc:
            self.error.emit(
                f"Installation failed (exit code {exc.returncode}):\n"
                f"{exc.stderr or exc.stdout or str(exc)}"
            )
        except Exception as exc:
            self.error.emit(f"Installation failed: {exc}")

    # -- Manifest tracking for .desktop/icon cleanup on uninstall -------
    # These thin wrappers delegate to app2nix.manifest (no PyQt6 dependency)
    # so the same logic can be used from the CLI.

    @staticmethod
    def _manifest_path() -> Path:
        from app2nix.manifest import manifest_path
        return manifest_path()

    @staticmethod
    def _load_manifest() -> dict:
        from app2nix.manifest import load_manifest
        return load_manifest()

    @staticmethod
    def _save_manifest(data: dict) -> None:
        from app2nix.manifest import save_manifest
        save_manifest(data)

    @classmethod
    def _record_install(cls, pkg_name: str, desktop_files: list[str],
                        icon_files: list[str],
                        nix_profile_key: str = "") -> None:
        from app2nix.manifest import record_install
        record_install(pkg_name, desktop_files, icon_files, nix_profile_key)

    @classmethod
    def _cleanup_orphaned_entries(cls) -> None:
        from app2nix.manifest import cleanup_orphaned_entries
        cleanup_orphaned_entries()

    def _install_desktop_files(self):
        """Find .desktop files in the installed Nix store path and copy to ~/.local/share/applications/."""
        # Clean up orphaned entries first
        try:
            self._cleanup_orphaned_entries()
        except Exception as exc:
            self.progress.emit(f"Warning: cleanup failed: {exc}")

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        # Track installed files for manifest
        installed_desktop_names: list[str] = []
        installed_icon_names: list[str] = []

        nix_profile_key, store_path = self._find_nix_profile_entry()
        if not store_path:
            self.progress.emit("Could not find installed package in Nix store, generating .desktop file...")
            self._generate_fallback_desktop(desktop_dir)
            self._refresh_desktop_database(desktop_dir)
            return

        self.progress.emit(f"Searching for .desktop files in {store_path}...")
        desktop_files = self._find_desktop_files_in_store(store_path)

        if not desktop_files:
            self.progress.emit("No .desktop files found in package, generating...")
            self._generate_fallback_desktop(desktop_dir)
        else:
            for df in desktop_files:
                content = df.read_text(encoding="utf-8", errors="replace")
                content = self._patch_desktop_categories(content)
                dest = desktop_dir / df.name
                dest.write_text(content, encoding="utf-8")
                installed_desktop_names.append(df.name)
                self.progress.emit(f"Installed desktop entry: {df.name}")

        # Record the install with the nix profile key for exact matching during cleanup
        try:
            self._record_install(
                self._pkg_name,
                installed_desktop_names,
                installed_icon_names,
                nix_profile_key=nix_profile_key,
            )
        except Exception as exc:
            self.progress.emit(f"Warning: failed to record install: {exc}")

        self._refresh_desktop_database(desktop_dir)

    def _find_nix_profile_entry(self) -> tuple[str, Path | None]:
        """Find the Nix profile element key and store path of the just-installed package."""
        safe_name = self._pkg_name.lower().replace(" ", "-")

        # Try nix profile list --json first (new Nix)
        try:
            result = self._run_cmd(["nix", "profile", "list", "--json"])
            import json
            data = json.loads(result.stdout)
            elements = data.get("elements", {})
            for key, elem in reversed(list(elements.items())):
                key_lower = key.lower()
                if safe_name in key_lower or self._pkg_name.lower() in key_lower:
                    paths = elem.get("storePaths", [])
                    if paths:
                        return key, Path(paths[0])
            # Fallback: return the last element if no name match
            for key, elem in reversed(list(elements.items())):
                paths = elem.get("storePaths", [])
                if paths:
                    return key, Path(paths[0])
        except Exception:
            pass

        # Try nix-env -q (legacy)
        try:
            result = self._run_cmd(["nix-env", "-q", "--out-path"])
            for line in result.stdout.splitlines():
                if self._pkg_name in line.lower():
                    parts = line.rsplit(" ", 1)
                    if len(parts) == 2 and parts[1].startswith("/nix/store/"):
                        return "", Path(parts[1])
        except Exception:
            pass

        return "", None

    def _find_nix_store_path(self) -> Path | None:
        """Find the Nix store path of the just-installed package."""
        _, store_path = self._find_nix_profile_entry()
        return store_path

    def _find_desktop_files_in_store(self, store_path: Path) -> list[Path]:
        """Find .desktop files in a Nix store path."""
        desktop_files: list[Path] = []
        search_dirs = [
            store_path / "share" / "applications",
        ]
        for search_dir in search_dirs:
            if search_dir.is_dir():
                for f in search_dir.rglob("*.desktop"):
                    desktop_files.append(f)

        # Broader fallback: search share/applications in nested store paths
        if not desktop_files:
            for share_app in store_path.glob("*/share/applications"):
                if share_app.is_dir():
                    for f in share_app.rglob("*.desktop"):
                        if "mimeinfo" not in f.name.lower():
                            desktop_files.append(f)

        return desktop_files

    def _patch_desktop_categories(self, content: str) -> str:
        """Ensure the .desktop file has proper Categories for the desktop menu."""
        lines = content.splitlines(keepends=True)
        has_categories = False
        category = _guess_category(self._pkg_name)
        if not category.endswith(";"):
            category += ";"

        patched: list[str] = []
        for line in lines:
            if line.strip().startswith("Categories="):
                has_categories = True
                existing = line.split("=", 1)[1].strip()
                if not existing or existing == ";":
                    patched.append(f"Categories={category}\n")
                else:
                    if not existing.endswith(";"):
                        patched.append(f"Categories={existing};\n")
                    else:
                        patched.append(line)
            else:
                patched.append(line)

        if not has_categories:
            inserted = False
            for i, line in enumerate(patched):
                if line.strip().startswith("[Desktop Action"):
                    patched.insert(i, f"Categories={category}\n")
                    inserted = True
                    break
            if not inserted:
                patched.append(f"Categories={category}\n")

        return "".join(patched)

    def _generate_fallback_desktop(self, desktop_dir: Path):
        """Generate a .desktop file when the package doesn't include one."""
        safe_name = self._pkg_name.lower().replace(" ", "-")
        category = _guess_category(self._pkg_name)
        if not category.endswith(";"):
            category += ";"

        exec_path = self._find_main_executable()
        exec_line = exec_path if exec_path else str(Path.home() / ".nix-profile" / "bin" / safe_name)

        content = f"""[Desktop Entry]
Type=Application
Name={self._pkg_name}
Comment={self._pkg_name} v{self._version} (installed via app2nix)
Exec={exec_line}
Icon={safe_name}
Terminal=false
Categories={category}
StartupNotify=true
"""
        desktop_file = desktop_dir / f"{safe_name}.desktop"
        desktop_file.write_text(content, encoding="utf-8")
        self.progress.emit(f"Generated desktop entry: {desktop_file.name}")

    def _find_main_executable(self) -> str | None:
        """Find the main executable path for the installed package."""
        safe_name = self._pkg_name.lower().replace(" ", "-")

        # Check nix profile bin paths (modern Nix)
        for profile_dir in [
            Path.home() / ".local" / "state" / "nix" / "profiles",
            Path.home() / ".nix-profile",
        ]:
            profile_bin = profile_dir / "bin"
            if profile_bin.is_dir():
                candidate = profile_bin / safe_name
                if candidate.is_file():
                    return str(candidate)
                for f in profile_bin.iterdir():
                    if safe_name in f.name.lower():
                        return str(f)

        pkg_dir = Path.home() / "nix-packages" / self._pkg_name
        if pkg_dir.is_dir():
            for f in pkg_dir.rglob("bin/*"):
                if f.is_file() and os.access(f, os.X_OK):
                    return str(f)

        return None

    @staticmethod
    def _patch_desktop_icon(content: str, icon_name: str) -> str:
        """Replace or add the Icon= line in a .desktop file content."""
        lines = content.splitlines(keepends=True)
        patched: list[str] = []
        found = False
        for line in lines:
            if line.strip().startswith("Icon="):
                patched.append(f"Icon={icon_name}\n")
                found = True
            else:
                patched.append(line)
        if not found:
            patched.append(f"Icon={icon_name}\n")
        return "".join(patched)

    @staticmethod
    def _find_icons_in_store(store_path: Path) -> list[Path]:
        """Find icon files (.png, .svg, .xpm, .ico) in a Nix store path."""
        icon_exts = {".png", ".svg", ".xpm", ".ico"}
        icons: list[Path] = []
        icons_dirs = [
            store_path / "share" / "icons",
        ]
        for icons_dir in icons_dirs:
            if icons_dir.is_dir():
                for f in icons_dir.rglob("*"):
                    if f.is_file() and f.suffix.lower() in icon_exts:
                        icons.append(f)

        # Broader fallback: search share/icons in nested store paths
        if not icons:
            for share_icons in store_path.glob("**/share/icons"):
                if share_icons.is_dir():
                    for f in share_icons.rglob("*"):
                        if f.is_file() and f.suffix.lower() in icon_exts:
                            icons.append(f)

        return icons

    def _refresh_desktop_database(self, desktop_dir: Path):
        """Run update-desktop-database to refresh the application menu."""
        try:
            self._run_cmd(["update-desktop-database", str(desktop_dir)])
            self.progress.emit("Desktop menu database updated.")
        except Exception:
            pass

    def _run_cmd(self, cmd: list[str], stdin_data: str | None = None,
                 env: dict | None = None):
        """Run a command, optionally piping stdin_data."""
        full_env = {**os.environ, **(env or {})}
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=600,
            env=full_env,
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd,
                output=proc.stdout, stderr=proc.stderr,
            )
        return proc


# ---------------------------------------------------------------------------
# Sudo password dialog
# ---------------------------------------------------------------------------

class SudoPasswordDialog(QDialog):
    """Simple dialog to ask for the sudo password."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sudo Password Required")
        self.setFixedSize(400, 160)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel(
            "System installation requires administrator privileges.\n"
            "Enter your sudo password to continue:"
        )
        layout.addWidget(label)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password")
        self.password_input.returnPressed.connect(self.accept)
        layout.addWidget(self.password_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("Install")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def get_password(self) -> str | None:
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.password_input.text()
        return None


# ---------------------------------------------------------------------------
# Scrollable container helper
# ---------------------------------------------------------------------------

def _make_scrollable(widget: QWidget) -> QScrollArea:
    """Wrap a widget in a QScrollArea."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(widget)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return scroll


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class App2NixWindow(QWidget):
    """Main window for converting Linux packages to NixOS expressions."""

    # -- Constructor -------------------------------------------------------

    # -- Class-level widget attributes (declared for mypy) --
    lbl_name: QLabel
    lbl_version: QLabel
    lbl_format: QLabel
    lbl_arch: QLabel
    file_path: QLineEdit
    output_area: QTextEdit
    status_bar: QLabel
    progress_bar: QProgressBar
    analyze_btn: QPushButton
    clear_btn: QPushButton
    gen_default_btn: QPushButton
    gen_flake_btn: QPushButton
    install_btn: QPushButton
    system_install_cb: QCheckBox
    theme_btn: QPushButton
    lang_combo: QComboBox
    tabs: QTabWidget
    lbl_header_subtitle: QLabel

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mainWidget")

        # State
        self.current_file: str | None = None
        self._analysis_result = None
        self._worker: AnalyzeWorker | None = None
        self._install_worker: InstallWorker | None = None
        self._theme_mode = "light"
        self._current_lang = current_lang()

        self._build_ui()
        self._apply_theme("light")
        self._connect_signals()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle(tr("window.title", "app2nix — Package to NixOS Converter"))
        self.setMinimumSize(860, 720)
        self.setBaseSize(920, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Header --------------------------------------------------------
        header = QWidget()
        header.setObjectName("headerWidget")
        header.setFixedHeight(80)

        hdr = QHBoxLayout(header)
        hdr.setContentsMargins(24, 14, 24, 14)

        # Logo + title
        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        icon = QLabel("🛠️")
        icon.setStyleSheet("font-size: 22px;")
        title_row.addWidget(icon)

        self.lbl_header_title = QLabel("app2nix")
        self.lbl_header_title.setObjectName("headerTitle")
        title_row.addWidget(self.lbl_header_title)

        title_col.addLayout(title_row)

        self.lbl_header_subtitle = QLabel(
            tr("app.subtitle", "Convert any Linux package to a NixOS expression")
        )
        self.lbl_header_subtitle.setObjectName("headerSubtitle")
        title_col.addWidget(self.lbl_header_subtitle)

        hdr.addLayout(title_col, 1)

        # Right side: language selector + theme toggle
        right_row = QHBoxLayout()
        right_row.setSpacing(8)

        # Language selector
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("langCombo")
        self.lang_combo.setFixedWidth(120)
        for code, name in available_langs():
            self.lang_combo.addItem(name, code)
        # Set current language
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == self._current_lang:
                self.lang_combo.setCurrentIndex(i)
                break
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        right_row.addWidget(self.lang_combo)

        # Theme toggle
        self.theme_btn = QPushButton("🌙" if self._theme_mode == "light" else "☀️")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.setToolTip("Toggle dark/light theme")
        right_row.addWidget(self.theme_btn)

        hdr.addLayout(right_row)
        layout.addWidget(header)

        # -- Tab widget ----------------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        self.tabs.addTab(self._build_convert_tab(), tr("tab.convert", "🔄 Convert"))
        self.tabs.addTab(self._build_help_tab(), tr("tab.help", "📖 Help"))
        self.tabs.addTab(self._build_about_tab(), tr("tab.about", "ℹ️ About"))

        layout.addWidget(self.tabs, 1)

    # -- Convert tab -------------------------------------------------------

    def _build_convert_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("convertTab")
        root = QVBoxLayout(tab)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        # -- File selection ------------------------------------------------
        root.addWidget(self._section_label(tr("package.input", "PACKAGE FILE")))

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText(
            tr("file.placeholder",
               "Select a .deb, .rpm, .AppImage, .flatpak, .snap or archive…")
        )
        self.file_path.setObjectName("filePathInput")
        file_row.addWidget(self.file_path, 1)

        self.browse_btn = QPushButton(tr("file.browse", "Browse…"))
        self.browse_btn.setObjectName("browseBtn")
        file_row.addWidget(self.browse_btn)
        root.addLayout(file_row)

        # -- Package info (auto-populated) ---------------------------------
        root.addWidget(self._section_label(tr("info.name", "PACKAGE INFO").replace("Name:", "INFO").upper()))

        info_frame = QFrame()
        info_frame.setObjectName("infoFrame")
        info_grid = QHBoxLayout(info_frame)
        info_grid.setContentsMargins(16, 12, 16, 12)
        info_grid.setSpacing(24)

        for label_text, attr in [
            (tr("info.name", "Name:"), "lbl_name"),
            (tr("info.version", "Version:"), "lbl_version"),
            (tr("info.format", "Format:"), "lbl_format"),
            (tr("info.arch", "Architecture:"), "lbl_arch"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setObjectName("infoKey")
            col.addWidget(lbl)
            val = QLabel("—")
            val.setObjectName("infoValue")
            setattr(self, attr, val)
            col.addWidget(val)
            info_grid.addLayout(col)

        root.addWidget(info_frame)

        # -- Action buttons ------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.analyze_btn = QPushButton(tr("analyze.btn", "🔍 Analyze"))
        self.analyze_btn.setObjectName("analyzeBtn")
        self.analyze_btn.setEnabled(True)
        btn_row.addWidget(self.analyze_btn)

        self.clear_btn = QPushButton(tr("clear.btn", "🗑️ Clear"))
        self.clear_btn.setObjectName("clearBtn")
        btn_row.addWidget(self.clear_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

        # -- Separator -----------------------------------------------------
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # -- Output area ---------------------------------------------------
        root.addWidget(self._section_label(tr("tab.results", "NIX EXPRESSION")))

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setPlaceholderText(
            "Analysis results will appear here…\n"
            "Select a package file and click Analyze."
        )
        self.output_area.setMinimumHeight(140)
        root.addWidget(self.output_area, 1)

        # -- Generate + Install buttons ------------------------------------
        gen_row = QHBoxLayout()
        gen_row.setSpacing(8)

        self.gen_default_btn = QPushButton(tr("gen.default_btn", "📄 Generate default.nix"))
        self.gen_default_btn.setObjectName("genBtn")
        self.gen_default_btn.setEnabled(False)
        gen_row.addWidget(self.gen_default_btn)

        self.gen_flake_btn = QPushButton(tr("gen.flake_btn", "❄️ Generate flake.nix"))
        self.gen_flake_btn.setObjectName("genBtn")
        self.gen_flake_btn.setEnabled(False)
        gen_row.addWidget(self.gen_flake_btn)

        gen_row.addStretch()

        self.system_install_cb = QCheckBox(tr("install.system_cb", "System install (sudo)"))
        self.system_install_cb.setToolTip(
            tr("install.system_tip", "Install system-wide using sudo.\nUnchecked = user install (nix profile install).")
        )
        gen_row.addWidget(self.system_install_cb)

        self.install_btn = QPushButton(tr("install.btn", "⬇️ Install on NixOS"))
        self.install_btn.setObjectName("installBtn")
        self.install_btn.setEnabled(False)
        gen_row.addWidget(self.install_btn)

        root.addLayout(gen_row)

        # -- Progress bar --------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # -- Status bar ----------------------------------------------------
        self.status_bar = QLabel(tr("status.ready", "Ready"))
        self.status_bar.setObjectName("statusBar")
        root.addWidget(self.status_bar)

        return tab

    # -- Help tab (Support Assistant) --------------------------------------

    def _build_help_tab(self) -> QWidget:
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(0, 0, 0, 0)

        # Scrollable content
        content = QWidget()
        content.setObjectName("helpContent")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(16)

        # Title
        title = QLabel(tr("help.title", "Help & Support"))
        title.setObjectName("helpTitle")
        lay.addWidget(title)

        subtitle = QLabel(tr("help.subtitle", "Everything you need to get started with app2nix"))
        subtitle.setObjectName("helpSubtitle")
        lay.addWidget(subtitle)

        # ── Quick Start Guide ──
        lay.addWidget(self._help_section_header(tr("help.quick_start", "Quick Start Guide")))

        steps = [
            (tr("help.step1_title", "1. Select a Package"),
             tr("help.step1_desc", "Click 'Browse' to select a Linux package file (.deb, .rpm, .AppImage, .flatpak, .snap, .tar.gz, .zip) or drag and drop it.")),
            (tr("help.step2_title", "2. Analyze"),
             tr("help.step2_desc", "Click 'Analyze' to detect the package format, extract dependencies, and generate a NixOS expression automatically.")),
            (tr("help.step3_title", "3. Review & Edit"),
             tr("help.step3_desc", "Review the generated Nix expression. You can edit it directly in the editor, then save it as default.nix or flake.nix.")),
            (tr("help.step4_title", "4. Install"),
             tr("help.step4_desc", "Click 'Install on NixOS' to build and install the package directly, or use the saved .nix file with nix-env or nixos-rebuild.")),
        ]

        for step_title, step_desc in steps:
            card = QFrame()
            card.setObjectName("helpStepCard")
            card_lay = QHBoxLayout(card)
            card_lay.setContentsMargins(16, 12, 16, 12)
            card_lay.setSpacing(12)

            step_title_lbl = QLabel(step_title)
            step_title_lbl.setObjectName("helpStepTitle")
            step_title_lbl.setFixedWidth(200)
            card_lay.addWidget(step_title_lbl)

            step_desc_lbl = QLabel(step_desc)
            step_desc_lbl.setObjectName("helpStepDesc")
            step_desc_lbl.setWordWrap(True)
            card_lay.addWidget(step_desc_lbl, 1)

            lay.addWidget(card)

        # ── Supported Formats ──
        lay.addWidget(self._help_section_header(tr("help.formats_title", "Supported Formats")))

        formats_desc = QLabel(tr("help.formats_desc", "app2nix supports the following package formats:"))
        formats_desc.setObjectName("helpText")
        lay.addWidget(formats_desc)

        formats_frame = QFrame()
        formats_frame.setObjectName("helpFormatsFrame")
        fmt_lay = QHBoxLayout(formats_frame)
        fmt_lay.setContentsMargins(16, 12, 16, 12)
        fmt_lay.setSpacing(8)

        format_emojis = [
            (".deb", "📦", "Debian/Ubuntu"),
            (".rpm", "📦", "Fedora/RHEL"),
            (".AppImage", "🚀", "Portable apps"),
            (".flatpak", "📦", "Flatpak"),
            (".snap", "📦", "Snap"),
            (".tar.gz", "📦", "Archives"),
            (".zip", "📦", "ZIP archives"),
        ]

        for ext, emoji, desc in format_emojis:
            fmt_col = QVBoxLayout()
            fmt_col.setAlignment(Qt.AlignmentFlag.AlignTop)
            fmt_col.setSpacing(2)
            emoji_lbl = QLabel(emoji)
            emoji_lbl.setStyleSheet("font-size: 20px;")
            emoji_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fmt_col.addWidget(emoji_lbl)
            ext_lbl = QLabel(ext)
            ext_lbl.setObjectName("helpFormatExt")
            ext_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fmt_col.addWidget(ext_lbl)
            desc_lbl = QLabel(desc)
            desc_lbl.setObjectName("helpFormatDesc")
            desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fmt_col.addWidget(desc_lbl)
            fmt_lay.addLayout(fmt_col)

        fmt_lay.addStretch()
        lay.addWidget(formats_frame)

        # ── FAQ ──
        lay.addWidget(self._help_section_header(tr("help.faq_title", "Frequently Asked Questions")))

        faqs = [
            (tr("help.faq1_q", "What is app2nix?"),
             tr("help.faq1_a", "app2nix converts Linux packages (.deb, .rpm, .AppImage, etc.) into NixOS expressions, allowing you to install any Linux package on NixOS.")),
            (tr("help.faq2_q", "Why do I get 'webkitgtk_4_0 has been removed'?"),
             tr("help.faq2_a", "This error means the package depends on an old WebKit version. app2nix automatically maps it to the newer webkitgtk_4_1. If the package still fails, it may need code changes by the upstream developer.")),
            (tr("help.faq3_q", "How do I install a .deb package?"),
             tr("help.faq3_a", "Simply browse for the .deb file, click Analyze, review the generated Nix expression, and click Install. app2nix handles dpkg extraction automatically.")),
            (tr("help.faq4_q", "Can I install packages system-wide?"),
             tr("help.faq4_a", "Yes! Check the 'System install (sudo)' checkbox before clicking Install. You'll be prompted for your sudo password.")),
            (tr("help.faq5_q", "What if a dependency can't be resolved?"),
             tr("help.faq5_a", "Some uncommon libraries may not have a NixOS equivalent. The unresolved dependencies will be listed after analysis. You may need to find the Nix package name manually on search.nixos.org.")),
        ]

        for faq_q, faq_a in faqs:
            faq_card = QFrame()
            faq_card.setObjectName("helpFaqCard")
            faq_lay = QVBoxLayout(faq_card)
            faq_lay.setContentsMargins(16, 12, 16, 12)
            faq_lay.setSpacing(6)

            q_lbl = QLabel(f"❓ {faq_q}")
            q_lbl.setObjectName("helpFaqQ")
            q_lbl.setWordWrap(True)
            faq_lay.addWidget(q_lbl)

            a_lbl = QLabel(f"  {faq_a}")
            a_lbl.setObjectName("helpFaqA")
            a_lbl.setWordWrap(True)
            faq_lay.addWidget(a_lbl)

            lay.addWidget(faq_card)

        # ── Tips & Troubleshooting ──
        lay.addWidget(self._help_section_header(tr("help.tips_title", "Tips & Troubleshooting")))

        tips = [
            (tr("help.tip1_title", "Root permissions"),
             tr("help.tip1_desc", "If you get a sandbox error, your root directory may be world-writable. Fix with: sudo chmod 755 /")),
            (tr("help.tip2_title", "Unfree packages"),
             tr("help.tip2_desc", "app2nix automatically sets NIXPKGS_ALLOW_UNFREE=1 during installation.")),
            (tr("help.tip3_title", "Desktop integration"),
             tr("help.tip3_desc", "After installation, app2nix automatically installs .desktop files so the app appears in your application menu.")),
        ]

        for tip_title, tip_desc in tips:
            tip_card = QFrame()
            tip_card.setObjectName("helpTipCard")
            tip_lay = QHBoxLayout(tip_card)
            tip_lay.setContentsMargins(16, 12, 16, 12)
            tip_lay.setSpacing(12)

            tip_t = QLabel(f"💡 {tip_title}")
            tip_t.setObjectName("helpTipTitle")
            tip_t.setFixedWidth(200)
            tip_lay.addWidget(tip_t)

            tip_d = QLabel(tip_desc)
            tip_d.setObjectName("helpTipDesc")
            tip_d.setWordWrap(True)
            tip_lay.addWidget(tip_d, 1)

            lay.addWidget(tip_card)

        # ── Contact / Links ──
        lay.addWidget(self._help_section_header(tr("help.contact_title", "Need more help?")))

        contact_card = QFrame()
        contact_card.setObjectName("helpContactCard")
        contact_lay = QVBoxLayout(contact_card)
        contact_lay.setContentsMargins(16, 12, 16, 12)
        contact_lay.setSpacing(8)

        contact_lbl = QLabel(
            tr("help.contact_desc", "Visit our documentation or open an issue on GitHub:")
        )
        contact_lbl.setObjectName("helpText")
        contact_lay.addWidget(contact_lbl)

        links_row = QHBoxLayout()
        links_row.setSpacing(8)

        for label_text, url in [
            (tr("help.link_docs", "📖 Documentation"), "https://github.com/HiTechTN/app2nix#readme"),
            (tr("help.link_bug", "🐛 Report Bug"), "https://github.com/HiTechTN/app2nix/issues"),
            (tr("help.link_github", "⭐ GitHub"), "https://github.com/HiTechTN/app2nix"),
        ]:
            btn = QPushButton(label_text)
            btn.setObjectName("helpLinkBtn")
            btn.clicked.connect(lambda checked, u=url: QDesktopServices.openUrl(QUrl(u)))
            links_row.addWidget(btn)

        links_row.addStretch()
        contact_lay.addLayout(links_row)
        lay.addWidget(contact_card)

        lay.addStretch()

        scroll = _make_scrollable(content)
        root.addWidget(scroll)
        return tab

    # -- About tab ---------------------------------------------------------

    def _build_about_tab(self) -> QWidget:
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        content.setObjectName("aboutContent")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(40, 30, 40, 30)
        lay.setSpacing(16)

        # App icon + title
        icon_lbl = QLabel("🛠️")
        icon_lbl.setStyleSheet("font-size: 48px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        name_lbl = QLabel("app2nix")
        name_lbl.setObjectName("aboutName")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name_lbl)

        desc_lbl = QLabel(tr("about.desc", "Universal Package to NixOS Converter"))
        desc_lbl.setObjectName("aboutDesc")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(desc_lbl)

        version_lbl = QLabel(tr("about.version", "Version 3.1.0"))
        version_lbl.setObjectName("aboutVersion")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(version_lbl)

        # Separator
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        # Info cards
        info_items = [
            ("👤", tr("about.author", "Contributors"), "app2nix contributors"),
            ("📜", tr("about.license", "License"), "MIT License"),
            ("💻", tr("about.credits", "Built with"), "Python, PyQt6, Rust, and Nix"),
            ("❤️", tr("about.thanks", "Thanks"), "The NixOS community"),
        ]

        for emoji, label, value in info_items:
            info_row = QHBoxLayout()
            info_row.setSpacing(12)
            emoji_lbl = QLabel(emoji)
            emoji_lbl.setStyleSheet("font-size: 18px;")
            emoji_lbl.setFixedWidth(30)
            info_row.addWidget(emoji_lbl)
            col = QVBoxLayout()
            col.setSpacing(1)
            key_lbl = QLabel(label)
            key_lbl.setObjectName("aboutKey")
            col.addWidget(key_lbl)
            val_lbl = QLabel(value)
            val_lbl.setObjectName("aboutValue")
            col.addWidget(val_lbl)
            info_row.addLayout(col, 1)
            lay.addLayout(info_row)

        # Separator
        sep2 = QFrame()
        sep2.setObjectName("separator")
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        lay.addWidget(sep2)

        # Links
        links_row = QHBoxLayout()
        links_row.setSpacing(8)
        links_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for label_text, url in [
            ("📖 " + tr("about.docs", "Documentation"), "https://github.com/HiTechTN/app2nix#readme"),
            ("🐛 " + tr("about.bug_report", "Report a Bug"), "https://github.com/HiTechTN/app2nix/issues"),
            ("💻 " + tr("about.github", "GitHub"), "https://github.com/HiTechTN/app2nix"),
        ]:
            btn = QPushButton(label_text)
            btn.setObjectName("aboutLinkBtn")
            btn.clicked.connect(lambda checked, u=url: QDesktopServices.openUrl(QUrl(u)))
            links_row.addWidget(btn)

        lay.addLayout(links_row)

        lay.addStretch()

        scroll = _make_scrollable(content)
        root.addWidget(scroll)
        return tab

    # -- Helpers -----------------------------------------------------------

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _help_section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("helpSectionHeader")
        return lbl

    # -- Styling -----------------------------------------------------------

    def _apply_theme(self, mode: str):
        set_theme(mode)
        t = get_theme()

        # Validate required theme keys -- fallback to LIGHT defaults for any missing
        missing = _REQUIRED_THEME_KEYS - t.keys()
        if missing:
            from app2nix.gui.theme import LIGHT
            t = {**LIGHT, **t}

        h = t["header_start"]
        he = t["header_end"]
        tab_bg = t.get("tab_bg", t["bg"])
        tab_text = t.get("tab_text", t["text_muted"])
        tab_sel = t.get("tab_selected", t["accent"])
        t.get("tab_border", t["separator"])
        help_card_bg = t.get("help_card_bg", t["card_bg"])
        help_card_bdr = t.get("help_card_border", t["card_border"])
        help_step_bg = t.get("help_step_bg", t["card_bg"])
        help_step_bdr = t.get("help_step_border", t["card_border"])

        style = f"""
        QWidget#mainWidget {{
            font-family: "Segoe UI", "SF Pro", system-ui, sans-serif;
            background: {t["bg"]};
        }}
        QWidget#headerWidget {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {h}, stop:1 {he});
        }}
        QLabel#headerTitle {{
            font-size: 22px;
            font-weight: 700;
            letter-spacing: 0.3px;
            color: {t["header_text"]};
        }}
        QLabel#headerSubtitle {{
            font-size: 13px;
            color: {t["header_subtitle"]};
            margin-top: 2px;
        }}
        QLabel#sectionLabel {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: {t["text_muted"]};
            padding-bottom: 4px;
        }}
        QLabel#infoKey {{
            font-size: 11px;
            font-weight: 500;
            color: {t["text_muted"]};
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        QLabel#infoValue {{
            font-size: 14px;
            font-weight: 600;
            color: {t["text_primary"]};
            padding: 2px 0;
        }}
        QFrame#infoFrame {{
            background: {help_card_bg};
            border: 1px solid {help_card_bdr};
            border-radius: 8px;
        }}

        /* ── Tabs ── */
        QTabWidget#mainTabs::pane {{
            border: none;
            background: {t["bg"]};
        }}
        QTabBar::tab {{
            background: {tab_bg};
            color: {tab_text};
            border: none;
            border-bottom: 3px solid transparent;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 600;
            min-width: 100px;
        }}
        QTabBar::tab:selected {{
            color: {tab_sel};
            border-bottom: 3px solid {tab_sel};
            background: {t["bg"]};
        }}
        QTabBar::tab:hover {{
            color: {tab_sel};
            background: {tab_bg};
        }}

        /* ── Inputs ── */
        QLineEdit {{
            padding: 8px 12px;
            border: 1px solid {t["input_border"]};
            border-radius: 6px;
            background: {t["input_bg"]};
            color: {t["text_primary"]};
            font-size: 14px;
            selection-background-color: {t["accent"]};
        }}
        QLineEdit:focus {{
            border: 2px solid {t["input_focus"]};
            padding: 7px 11px;
        }}

        /* ── Buttons ── */
        QPushButton {{
            padding: 8px 18px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton#analyzeBtn {{
            background: {t["success"]};
            color: #ffffff;
            border: none;
        }}
        QPushButton#analyzeBtn:hover {{
            background: {t["success_hover"]};
        }}
        QPushButton#analyzeBtn:disabled {{
            background: {t["progress_bg"]};
            color: {t["text_muted"]};
        }}
        QPushButton#clearBtn {{
            background: {t["btn_sec_bg"]};
            color: {t["btn_sec_text"]};
            border: 1px solid {t["btn_sec_border"]};
        }}
        QPushButton#clearBtn:hover {{
            background: {t["btn_sec_hover"]};
        }}
        QPushButton#themeBtn {{
            background: rgba(255,255,255,0.15);
            border: none;
            border-radius: 18px;
            font-size: 16px;
            padding: 0;
        }}
        QPushButton#themeBtn:hover {{
            background: rgba(255,255,255,0.25);
        }}
        QPushButton#browseBtn {{
            background: {t["accent"]};
            color: #ffffff;
            border: none;
            min-width: 80px;
        }}
        QPushButton#browseBtn:hover {{
            background: {t["accent_hover"]};
        }}
        QPushButton#genBtn {{
            background: {t["accent"]};
            color: #ffffff;
            border: none;
            padding: 8px 22px;
        }}
        QPushButton#genBtn:hover {{
            background: {t["accent_hover"]};
        }}
        QPushButton#genBtn:disabled {{
            background: {t["progress_bg"]};
            color: {t["text_muted"]};
        }}
        QPushButton#installBtn {{
            background: #e67e22;
            color: #ffffff;
            border: none;
            padding: 8px 22px;
        }}
        QPushButton#installBtn:hover {{
            background: #d35400;
        }}
        QPushButton#installBtn:disabled {{
            background: {t["progress_bg"]};
            color: {t["text_muted"]};
        }}
        QPushButton#helpLinkBtn, QPushButton#aboutLinkBtn {{
            background: {t["accent"]};
            color: #ffffff;
            border: none;
            padding: 8px 16px;
        }}
        QPushButton#helpLinkBtn:hover, QPushButton#aboutLinkBtn:hover {{
            background: {t["accent_hover"]};
        }}

        /* ── Language combo ── */
        QComboBox#langCombo {{
            padding: 4px 8px;
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 4px;
            background: rgba(255,255,255,0.15);
            color: {t["header_text"]};
            font-size: 12px;
        }}
        QComboBox#langCombo::drop-down {{
            border: none;
        }}
        QComboBox#langCombo QAbstractItemView {{
            background: {t["card_bg"]};
            color: {t["text_primary"]};
            border: 1px solid {t["card_border"]};
            selection-background-color: {t["accent"]};
        }}

        /* ── Separator ── */
        QFrame#separator {{
            max-height: 1px;
            border: none;
            background: {t["separator"]};
            margin: 8px 0;
        }}

        /* ── Output area ── */
        QTextEdit {{
            background: {t["card_bg"]};
            border: 1px solid {t["card_border"]};
            border-radius: 6px;
            color: {t["text_primary"]};
            font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", monospace;
            font-size: 12px;
            padding: 10px;
            selection-background-color: {t["accent"]};
        }}

        /* ── Status & progress ── */
        QLabel#statusBar {{
            font-size: 12px;
            color: {t["text_muted"]};
            padding: 4px 0;
        }}
        QProgressBar#progressBar {{
            border: none;
            background: {t["progress_bg"]};
            border-radius: 2px;
        }}
        QProgressBar#progressBar::chunk {{
            background: {t["accent"]};
            border-radius: 2px;
        }}
        QCheckBox {{
            font-size: 13px;
            color: {t["text_primary"]};
        }}

        /* ── Help tab ── */
        QWidget#helpContent {{
            background: {t["bg"]};
        }}
        QLabel#helpTitle {{
            font-size: 22px;
            font-weight: 700;
            color: {t["text_primary"]};
        }}
        QLabel#helpSubtitle {{
            font-size: 14px;
            color: {t["text_muted"]};
            margin-bottom: 8px;
        }}
        QLabel#helpSectionHeader {{
            font-size: 16px;
            font-weight: 700;
            color: {t["text_primary"]};
            padding: 8px 0 4px 0;
            border-bottom: 2px solid {t["accent"]};
        }}
        QFrame#helpStepCard {{
            background: {help_step_bg};
            border: 1px solid {help_step_bdr};
            border-radius: 8px;
        }}
        QLabel#helpStepTitle {{
            font-size: 14px;
            font-weight: 700;
            color: {t["accent"]};
        }}
        QLabel#helpStepDesc {{
            font-size: 13px;
            color: {t["text_primary"]};
            line-height: 1.4;
        }}
        QFrame#helpFormatsFrame {{
            background: {help_card_bg};
            border: 1px solid {help_card_bdr};
            border-radius: 8px;
        }}
        QLabel#helpFormatExt {{
            font-size: 11px;
            font-weight: 700;
            color: {t["accent"]};
        }}
        QLabel#helpFormatDesc {{
            font-size: 10px;
            color: {t["text_muted"]};
        }}
        QFrame#helpFaqCard {{
            background: {help_card_bg};
            border: 1px solid {help_card_bdr};
            border-radius: 8px;
        }}
        QLabel#helpFaqQ {{
            font-size: 14px;
            font-weight: 700;
            color: {t["text_primary"]};
        }}
        QLabel#helpFaqA {{
            font-size: 13px;
            color: {t["text_secondary"]};
            line-height: 1.4;
        }}
        QFrame#helpTipCard {{
            background: {help_step_bg};
            border: 1px solid {help_step_bdr};
            border-radius: 8px;
        }}
        QLabel#helpTipTitle {{
            font-size: 14px;
            font-weight: 700;
            color: {t["accent"]};
        }}
        QLabel#helpTipDesc {{
            font-size: 13px;
            color: {t["text_primary"]};
            line-height: 1.4;
        }}
        QFrame#helpContactCard {{
            background: {help_card_bg};
            border: 1px solid {help_card_bdr};
            border-radius: 8px;
        }}
        QLabel#helpText {{
            font-size: 13px;
            color: {t["text_primary"]};
        }}

        /* ── About tab ── */
        QWidget#aboutContent {{
            background: {t["bg"]};
        }}
        QLabel#aboutName {{
            font-size: 28px;
            font-weight: 800;
            color: {t["text_primary"]};
        }}
        QLabel#aboutDesc {{
            font-size: 16px;
            color: {t["text_secondary"]};
        }}
        QLabel#aboutVersion {{
            font-size: 14px;
            color: {t["accent"]};
            font-weight: 600;
        }}
        QLabel#aboutKey {{
            font-size: 12px;
            font-weight: 600;
            color: {t["text_muted"]};
        }}
        QLabel#aboutValue {{
            font-size: 14px;
            color: {t["text_primary"]};
        }}
        """
        self.setStyleSheet(style)

    # -- Signal connections ------------------------------------------------

    def _connect_signals(self):
        self.browse_btn.clicked.connect(self._browse_file)
        self.analyze_btn.clicked.connect(self._on_analyze_clicked)
        self.clear_btn.clicked.connect(self._clear_all)
        self.theme_btn.clicked.connect(self._toggle_theme)
        self.gen_default_btn.clicked.connect(self._save_default_nix)
        self.gen_flake_btn.clicked.connect(self._save_flake_nix)
        self.install_btn.clicked.connect(self._on_install_clicked)

    # -- Slots -------------------------------------------------------------

    def _on_language_changed(self, index: int):
        lang_code = self.lang_combo.currentData()
        if lang_code and lang_code != self._current_lang:
            load_lang(lang_code)
            self._current_lang = lang_code
            # Rebuild UI with new language
            self._rebuild_ui()

    def _rebuild_ui(self):
        """Rebuild the entire UI with current language settings."""
        # Save state
        old_file = self.current_file
        old_result = self._analysis_result

        # Clear and rebuild
        self.tabs.clear()
        self.layout()

        # Rebuild tabs
        self.tabs.addTab(self._build_convert_tab(), tr("tab.convert", "🔄 Convert"))
        self.tabs.addTab(self._build_help_tab(), tr("tab.help", "📖 Help"))
        self.tabs.addTab(self._build_about_tab(), tr("tab.about", "ℹ️ About"))

        # Reconnect signals
        self._connect_signals()

        # Restore state
        if old_file:
            self.current_file = old_file
            self.file_path.setText(old_file)
            self.lbl_name.setText(Path(old_file).stem)
        if old_result:
            self._analysis_result = old_result
            self.output_area.setText(old_result.nix_content)
            self.gen_default_btn.setEnabled(True)
            self.gen_flake_btn.setEnabled(True)
            self.install_btn.setEnabled(True)

        # Update header subtitle
        self.lbl_header_subtitle.setText(
            tr("app.subtitle", "Convert any Linux package to a NixOS expression")
        )

    def _browse_file(self):
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("window.select_file", "Select a package file"),
            str(Path.home()),
            (
                "Packages (*.deb *.rpm *.AppImage *.appimage *.flatpak *.snap"
                " *.tar.gz *.tgz *.tar *.tar.xz *.tar.bz2 *.zip);;All files (*)"
            ),
        )
        if path:
            self.file_path.setText(path)

    def _on_analyze_clicked(self):
        path = self.file_path.text().strip()
        if not path:
            QMessageBox.warning(
                self,
                tr("error.no_file", "No file selected"),
                tr("error.select_file", "Please select a package file first."),
            )
            return

        fmt = _detect_format(path)
        if not fmt:
            QMessageBox.warning(
                self,
                tr("error.unsupported", "Unsupported Format"),
                tr(
                    "error.unsupported_format",
                    "The selected file format is not supported.\nSupported: .deb, .rpm, .AppImage, .flatpak, .snap, .tar.gz, .tgz, .tar, .tar.xz, .tar.bz2, .zip",
                ),
            )
            return

        self._start_analysis(path)

    def _start_analysis(self, package_path: str):
        """Begin analysis of a package file in a background thread."""
        self.current_file = package_path
        self.analyze_btn.setEnabled(False)
        self.gen_default_btn.setEnabled(False)
        self.gen_flake_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.output_area.clear()
        self.status_bar.setText(f"⏳ Analyzing {Path(package_path).name}…")

        p = Path(package_path)
        self.lbl_name.setText(p.stem)
        ext = _detect_format(package_path)
        self.lbl_format.setText(ext or "—")
        self.lbl_version.setText("…")
        self.lbl_arch.setText("…")

        self._worker = AnalyzeWorker(package_path)
        self._worker.finished.connect(self._on_analysis_finished)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.start()

    def _on_analysis_finished(self, result):
        self._analysis_result = result
        info = result.package
        self.lbl_name.setText(info.name)
        self.lbl_version.setText(info.version)
        self.lbl_format.setText(info.format)
        self.lbl_arch.setText(info.architecture or "—")

        self.output_area.setText(result.nix_content)
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(True)
        self.gen_flake_btn.setEnabled(True)
        self.install_btn.setEnabled(True)
        self.status_bar.setText(
            f"✅ Analysis complete — {info.name} {info.version}"
        )

    def _on_analysis_error(self, error_msg: str):
        self.analyze_btn.setEnabled(True)
        self.status_bar.setText("❌ Analysis failed")
        QMessageBox.critical(
            self,
            tr("error.analysis", "Analysis Error"),
            f"{error_msg}",
        )

    def _clear_all(self):
        if self._worker is not None:
            try:
                self._worker.finished.disconnect(self._on_analysis_finished)
                self._worker.error.disconnect(self._on_analysis_error)
            except TypeError:
                pass
            self._worker = None

        if self._install_worker is not None:
            try:
                self._install_worker.progress.disconnect()
                self._install_worker.finished.disconnect()
                self._install_worker.error.disconnect()
            except TypeError:
                pass
            self._install_worker = None

        self.file_path.setText("")
        self.lbl_name.setText("—")
        self.lbl_version.setText("—")
        self.lbl_format.setText("—")
        self.lbl_arch.setText("—")
        self.output_area.clear()
        self.current_file = None
        self._analysis_result = None
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(False)
        self.gen_flake_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_bar.setText(tr("status.ready", "Ready"))

    def _toggle_theme(self):
        self._theme_mode = "dark" if self._theme_mode == "light" else "light"
        self._apply_theme(self._theme_mode)
        self.theme_btn.setText("☀️" if self._theme_mode == "dark" else "🌙")

    def _save_default_nix(self):
        if self._analysis_result:
            self._save_file("default.nix", self._analysis_result.nix_content)

    def _save_flake_nix(self):
        if not self._analysis_result:
            return
        try:
            from app2nix.core.generator import NixGenerator

            gen = NixGenerator()
            info = self._analysis_result.package
            flake_result = gen.generate_flake_nix(info)
            self._save_file("flake.nix", flake_result.nix_content)
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to generate flake.nix:\n{exc}"
            )

    def _save_file(self, filename: str, content: str):
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {filename}",
            str(Path.home() / filename),
            "Nix files (*.nix);;All files (*)",
        )
        if path:
            try:
                Path(path).write_text(content, encoding="utf-8")
                self.status_bar.setText(f"💾 Saved to {path}")
            except OSError as exc:
                QMessageBox.critical(
                    self,
                    tr("error.install", "Save Error"),
                    f"Failed to save {filename}:\n{exc}",
                )

    # -- Install -----------------------------------------------------------

    def _on_install_clicked(self):
        if not self._analysis_result or not self.current_file:
            return

        system_install = self.system_install_cb.isChecked()
        sudo_password = None

        if system_install:
            dlg = SudoPasswordDialog(self)
            sudo_password = dlg.get_password()
            if sudo_password is None:
                return

        self.install_btn.setEnabled(False)
        self.analyze_btn.setEnabled(False)
        self.gen_default_btn.setEnabled(False)
        self.gen_flake_btn.setEnabled(False)
        self.progress_bar.setVisible(True)

        info = self._analysis_result.package
        self._install_worker = InstallWorker(
            package_path=self.current_file,
            nix_content=self._analysis_result.nix_content,
            pkg_name=info.name,
            version=info.version,
            system_install=system_install,
            sudo_password=sudo_password,
        )
        self._install_worker.progress.connect(self._on_install_progress)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.error.connect(self._on_install_error)
        self._install_worker.start()

    def _on_install_progress(self, msg: str):
        self.status_bar.setText(f"⏳ {msg}")

    def _on_install_finished(self, msg: str):
        self.progress_bar.setVisible(False)
        self.install_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(True)
        self.gen_flake_btn.setEnabled(True)
        self.status_bar.setText(f"✅ {msg}")
        QMessageBox.information(
            self,
            tr("install.complete.title", "Installation Complete"),
            msg,
        )

    def _on_install_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.install_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(True)
        self.gen_flake_btn.setEnabled(True)
        self.status_bar.setText("❌ Install failed")
        QMessageBox.critical(
            self,
            tr("error.install", "Installation Failed"),
            msg,
        )
