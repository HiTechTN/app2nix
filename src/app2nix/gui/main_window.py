"""Main window for the app2nix graphical interface."""

import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

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
}

# Formats supported by the core analyzer
SUPPORTED_EXTENSIONS = {
    ".deb", ".rpm", ".appimage", ".flatpak",
    ".snap", ".tar.gz", ".tgz", ".tar",
    ".tar.xz", ".tar.bz2", ".zip",
}


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

            # Step 5: Build and install
            env = {"NIXPKGS_ALLOW_UNFREE": "1"}

            if self._system_install:
                self.progress.emit("Building and installing (system)...")
                cmd = [
                    "sudo", "-S",
                    "nix-env", "-f", str(nix_file), "-i",
                ]
                self._run_cmd(cmd, stdin_data=self._sudo_password + "\n", env=env)
            else:
                self.progress.emit("Building and installing (user)...")
                cmd = ["nix-env", "-f", str(nix_file), "-i"]
                self._run_cmd(cmd, env=env)

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

    def _run_cmd(self, cmd: list[str], stdin_data: str | None = None,
                 env: dict | None = None):
        """Run a command, optionally piping stdin_data."""
        import os
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
# Main application window
# ---------------------------------------------------------------------------

class App2NixWindow(QWidget):
    """Main window for converting Linux packages to NixOS expressions."""

    # -- Constructor -------------------------------------------------------

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mainWidget")

        # State
        self.current_file: str | None = None
        self._analysis_result = None
        self._worker: AnalyzeWorker | None = None
        self._install_worker: InstallWorker | None = None
        self._theme_mode = "light"

        self._build_ui()
        self._apply_theme("light")
        self._connect_signals()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle("app2nix — Package to NixOS Converter")
        self.setMinimumSize(720, 700)
        self.setBaseSize(780, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Header --------------------------------------------------------
        header = QWidget()
        header.setObjectName("headerWidget")
        header.setFixedHeight(90)

        hdr = QVBoxLayout(header)
        hdr.setContentsMargins(28, 16, 28, 12)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        icon = QLabel("\U0001f6e0\ufe0f")
        icon.setStyleSheet("font-size: 24px;")
        title_row.addWidget(icon)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.lbl_header_title = QLabel("app2nix")
        self.lbl_header_title.setObjectName("headerTitle")
        titles.addWidget(self.lbl_header_title)

        self.lbl_header_subtitle = QLabel("Convert Linux packages to NixOS expressions")
        self.lbl_header_subtitle.setObjectName("headerSubtitle")
        titles.addWidget(self.lbl_header_subtitle)

        title_row.addLayout(titles)
        title_row.addStretch()

        # Theme toggle
        self.theme_btn = QPushButton("\U0001f319" if self._theme_mode == "light" else "\u2600\ufe0f")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.setToolTip("Toggle dark/light theme")
        title_row.addWidget(self.theme_btn)

        hdr.addLayout(title_row)
        layout.addWidget(header)

        # -- Content area --------------------------------------------------
        content = QWidget()
        content.setObjectName("contentWidget")
        cont = QVBoxLayout(content)
        cont.setContentsMargins(28, 16, 28, 20)
        cont.setSpacing(14)

        # -- File selection ------------------------------------------------
        cont.addWidget(QLabel("\U0001f4e6  PACKAGE FILE"))
        self.section_file = QLabel("PACKAGE FILE")
        self.section_file.setObjectName("sectionLabel")

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Select a .deb, .rpm, .AppImage, .flatpak, .snap or archive\u2026")
        self.file_path.setObjectName("filePathInput")
        file_row.addWidget(self.file_path, 1)

        self.browse_btn = QPushButton("Browse\u2026")
        self.browse_btn.setObjectName("browseBtn")
        file_row.addWidget(self.browse_btn)

        cont.addLayout(file_row)

        # -- Package info (auto-populated) ---------------------------------
        self.section_info = QLabel("PACKAGE INFO")
        self.section_info.setObjectName("sectionLabel")
        cont.addWidget(self.section_info)

        info_grid = QVBoxLayout()
        info_grid.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(24)
        row1.addWidget(QLabel("Name:"), alignment=Qt.AlignmentFlag.AlignLeft)
        self.lbl_name = QLabel("-")
        self.lbl_name.setObjectName("infoValue")
        row1.addWidget(self.lbl_name, 1)
        row1.addWidget(QLabel("Version:"))
        self.lbl_version = QLabel("-")
        self.lbl_version.setObjectName("infoValue")
        row1.addWidget(self.lbl_version, 1)
        info_grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(24)
        row2.addWidget(QLabel("Format:"))
        self.lbl_format = QLabel("-")
        self.lbl_format.setObjectName("infoValue")
        row2.addWidget(self.lbl_format, 1)
        row2.addWidget(QLabel("Architecture:"))
        self.lbl_arch = QLabel("-")
        self.lbl_arch.setObjectName("infoValue")
        row2.addWidget(self.lbl_arch, 1)
        info_grid.addLayout(row2)

        cont.addLayout(info_grid)

        # -- Action buttons ------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.analyze_btn = QPushButton("\U0001f50d  Analyze")
        self.analyze_btn.setObjectName("analyzeBtn")
        self.analyze_btn.setEnabled(True)
        btn_row.addWidget(self.analyze_btn)

        self.clear_btn = QPushButton("\U0001f5d1\ufe0f  Clear")
        self.clear_btn.setObjectName("clearBtn")
        btn_row.addWidget(self.clear_btn)

        btn_row.addStretch()
        cont.addLayout(btn_row)

        # -- Separator -----------------------------------------------------
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedHeight(1)
        cont.addWidget(sep)

        # -- Output area ---------------------------------------------------
        self.section_output = QLabel("NIX EXPRESSION")
        self.section_output.setObjectName("sectionLabel")
        cont.addWidget(self.section_output)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setPlaceholderText(
            "Analysis results will appear here\u2026\n"
            "Select a package file and click Analyze."
        )
        self.output_area.setMinimumHeight(160)
        cont.addWidget(self.output_area, 1)

        # -- Generate + Install buttons ------------------------------------
        gen_row = QHBoxLayout()
        gen_row.setSpacing(10)

        self.gen_default_btn = QPushButton("\U0001f4c4  Generate default.nix")
        self.gen_default_btn.setObjectName("genBtn")
        self.gen_default_btn.setEnabled(False)
        gen_row.addWidget(self.gen_default_btn)

        self.gen_flake_btn = QPushButton("\u2744\ufe0f  Generate flake.nix")
        self.gen_flake_btn.setObjectName("genBtn")
        self.gen_flake_btn.setEnabled(False)
        gen_row.addWidget(self.gen_flake_btn)

        gen_row.addStretch()
        cont.addLayout(gen_row)

        # -- Install row ---------------------------------------------------
        install_row = QHBoxLayout()
        install_row.setSpacing(10)

        self.system_install_cb = QCheckBox("System install (sudo)")
        self.system_install_cb.setToolTip(
            "Install system-wide using sudo.\n"
            "Unchecked = user install (nix-env -i)."
        )
        install_row.addWidget(self.system_install_cb)

        self.install_btn = QPushButton("\u2b07\ufe0f  Install on NixOS")
        self.install_btn.setObjectName("installBtn")
        self.install_btn.setEnabled(False)
        install_row.addWidget(self.install_btn)

        install_row.addStretch()
        cont.addLayout(install_row)

        # -- Progress bar --------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setVisible(False)
        cont.addWidget(self.progress_bar)

        # -- Status bar ----------------------------------------------------
        self.status_bar = QLabel("Ready")
        self.status_bar.setObjectName("statusBar")
        cont.addWidget(self.status_bar)

        layout.addWidget(content, 1)

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
        style = f"""
        QWidget#mainWidget {{
            font-family: "Segoe UI", "SF Pro", system-ui, sans-serif;
            background: {t["bg"]};
        }}
        QWidget#headerWidget {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {h}, stop:1 {he});
        }}
        QWidget#contentWidget {{
            background: {t["bg"]};
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
        QLabel#infoValue {{
            font-size: 14px;
            font-weight: 500;
            color: {t["text_primary"]};
            padding: 2px 0;
        }}
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
        QFrame#separator {{
            max-height: 1px;
            border: none;
            background: {t["separator"]};
            margin: 8px 0;
        }}
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
                tr("window.error", "No file selected"),
                tr("error.no_file", "Please select a package file first."),
            )
            return

        fmt = _detect_format(path)
        if not fmt:
            QMessageBox.warning(
                self,
                tr("window.unsupported", "Unsupported format"),
                tr(
                    "error.unsupported_format",
                    "The selected file format is not supported.\n"
                    "Supported formats: .deb, .rpm, .AppImage, "
                    ".flatpak, .snap, .tar.gz, .tgz, .tar, .zip",
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
        self.status_bar.setText(f"\u23f3 Analyzing {Path(package_path).name}\u2026")

        # Update info labels with file name as placeholder
        p = Path(package_path)
        self.lbl_name.setText(p.stem)
        ext = _detect_format(package_path)
        self.lbl_format.setText(ext or "-")
        self.lbl_version.setText("\u2026")
        self.lbl_arch.setText("\u2026")

        self._worker = AnalyzeWorker(package_path)
        self._worker.finished.connect(self._on_analysis_finished)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.start()

    def _on_analysis_finished(self, result):
        self._analysis_result = result
        info = result.package  # type: ignore[union-attr]
        self.lbl_name.setText(info.name)
        self.lbl_version.setText(info.version)
        self.lbl_format.setText(info.format)
        self.lbl_arch.setText(info.architecture or "-")

        self.output_area.setText(result.nix_content)
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(True)
        self.gen_flake_btn.setEnabled(True)
        self.install_btn.setEnabled(True)
        self.status_bar.setText(
            f"\u2705 Analysis complete \u2014 {info.name} {info.version}"
        )

    def _on_analysis_error(self, error_msg: str):
        self.analyze_btn.setEnabled(True)
        self.status_bar.setText("\u274c Analysis failed")
        QMessageBox.critical(
            self,
            tr("window.error", "Analysis Error"),
            f"{error_msg}",
        )

    def _clear_all(self):
        # Disconnect worker signals to prevent race condition where
        # ``_on_analysis_finished`` / ``_on_analysis_error`` fires
        # after the user has already cleared the UI.
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
        self.lbl_name.setText("-")
        self.lbl_version.setText("-")
        self.lbl_format.setText("-")
        self.lbl_arch.setText("-")
        self.output_area.clear()
        self.current_file = None
        self._analysis_result = None
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(False)
        self.gen_flake_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_bar.setText("Ready")

    def _toggle_theme(self):
        self._theme_mode = "dark" if self._theme_mode == "light" else "light"
        self._apply_theme(self._theme_mode)
        self.theme_btn.setText("\u2600\ufe0f" if self._theme_mode == "dark" else "\U0001f319")

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
                self.status_bar.setText(f"\U0001f4be Saved to {path}")
            except OSError as exc:
                QMessageBox.critical(
                    self,
                    tr("window.error", "Save Error"),
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
                return  # user cancelled

        # Disable buttons during install
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
        self.status_bar.setText(f"\u23f3 {msg}")

    def _on_install_finished(self, msg: str):
        self.progress_bar.setVisible(False)
        self.install_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(True)
        self.gen_flake_btn.setEnabled(True)
        self.status_bar.setText(f"\u2705 {msg}")
        QMessageBox.information(
            self,
            "Installation Complete",
            msg,
        )

    def _on_install_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.install_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.gen_default_btn.setEnabled(True)
        self.gen_flake_btn.setEnabled(True)
        self.status_bar.setText(f"\u274c Install failed")
        QMessageBox.critical(
            self,
            "Installation Failed",
            msg,
        )
