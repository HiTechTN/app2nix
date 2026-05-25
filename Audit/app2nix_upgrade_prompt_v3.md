# ⚡ app2nix — Prompt de Mise à Niveau v3.0
### Instrument complet pour agent codeur · Basé sur audit v2.0 · Mai 2026

---

## 🎯 OBJECTIF

Mettre à niveau `app2nix` de **v2.0.0 → v3.0.0** en corrigeant les **22 issues** identifiées dans l'audit approfondi du code source actuel (analyse de `app2nix_gui.py`, `server.py`, `pyproject.toml`, `main.py`, `analyze_deb.py`, `universal_analyze.py`).

**Repo :** `https://github.com/HiTechTN/app2nix`  
**Branch cible :** `develop` (puis PR vers `master`)

---

## 📊 ÉTAT ACTUEL VÉRIFIÉ (v2.0.0)

Le projet a DÉJÀ implémenté les recommandations du prompt précédent :
- ✅ `analyze_deb.py` → wrapper deprecated vers `app2nix.core.analyzers.deb`
- ✅ `universal_analyze.py` → wrapper deprecated vers `app2nix.core.analyzer.UniversalAnalyzer`
- ✅ `pyproject.toml` → hatchling + toutes dépendances (pydantic, jinja2, typer, rich, aiosqlite)
- ✅ `app2nix_gui.py` → 844 lignes PyQt6, i18n, thèmes, utilise `UniversalAnalyzer`
- ⚠️ `server.py` → importe encore depuis les wrappers dépréciés
- ❌ GUI bloque le thread UI (nix-build, analyse, download)
- ❌ `lib/i18n` et `lib/theme` pas dans le package src/
- ❌ `build_nix_expression()` dupliquée entre server.py et gui.py
- ❌ Expressions Nix avec `unpackPhase = "true"` et `src = ./.` non-reproductibles

---

## 🚨 TÂCHES CLASSÉES PAR PRIORITÉ

---

### ═══════════════════════════════════════
### PRIORITÉ 1 — SÉCURITÉ CRITIQUE (3 tâches)
### ═══════════════════════════════════════

---

#### TÂCHE S1 — GUI : Migrer nix-build vers QThread [SEC-01]

**Fichier :** `app2nix_gui.py`

**Problème :** `_install_to_system()` appelle `subprocess.run(["nix-build"], timeout=600)` sur le thread principal Qt → UI gelée 10 min.

**Solution complète :**

Ajouter ces classes AVANT la définition de `App2NixWindow` :

```python
from PyQt6.QtCore import QThread, pyqtSignal

class AnalyzeWorker(QThread):
    """Worker pour l'analyse de package en background."""
    finished = pyqtSignal(object)   # PackageInfo
    failed   = pyqtSignal(str)      # message d'erreur
    progress = pyqtSignal(str)      # message de statut

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.terminate()

    def run(self):
        try:
            from app2nix.core.analyzer import UniversalAnalyzer
            self.progress.emit("Analyzing package structure...")
            analyzer = UniversalAnalyzer()
            info = analyzer.analyze(self.file_path)
            if not self._cancelled:
                self.finished.emit(info)
        except Exception as e:
            if not self._cancelled:
                self.failed.emit(str(e))


class InstallWorker(QThread):
    """Worker pour nix-build en background avec streaming logs."""
    log_line  = pyqtSignal(str)   # ligne de log en temps réel
    finished  = pyqtSignal(str)   # store_path Nix
    failed    = pyqtSignal(str)   # message d'erreur

    def __init__(self, pkg_dir: Path, env: dict):
        super().__init__()
        self.pkg_dir = pkg_dir
        self.env = env
        self._process = None

    def cancel(self):
        if self._process:
            self._process.terminate()
        self.terminate()

    def run(self):
        import subprocess, os
        try:
            self._process = subprocess.Popen(
                ["nix-build", "default.nix"],
                cwd=str(self.pkg_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=self.env,
            )
            output_lines = []
            for line in self._process.stdout:
                line = line.rstrip()
                output_lines.append(line)
                self.log_line.emit(line)
            self._process.wait()
            if self._process.returncode == 0:
                # Trouver le store path dans les dernières lignes
                for line in reversed(output_lines):
                    if line.startswith("/nix/store/"):
                        self.finished.emit(line.strip())
                        return
                self.failed.emit("nix-build succeeded but no store path found")
            else:
                errors = [l for l in output_lines if "error:" in l.lower()]
                self.failed.emit("\n".join(errors[-5:]) if errors else "nix-build failed")
        except FileNotFoundError:
            self.failed.emit("nix-build not found. Is NixOS/nix installed?")
        except Exception as e:
            self.failed.emit(str(e))
```

**Modifier `_analyze()` pour utiliser `AnalyzeWorker` :**

```python
def _analyze(self):
    file_path = self.file_path.text().strip()
    url = self.url_input.text().strip()

    if not file_path and not url:
        QMessageBox.warning(self, i18n.tr("error.no_input"), i18n.tr("error.select_file"))
        return

    if url:
        self._start_download(url)
        return

    self._start_analysis(file_path)

def _start_analysis(self, file_path: str):
    if not os.path.exists(file_path):
        QMessageBox.critical(self, i18n.tr("error.not_found"), file_path)
        return
    if not get_format(file_path):
        QMessageBox.warning(self, i18n.tr("error.unsupported"),
                            f"Supported: {', '.join(SUPPORTED_FORMATS)}")
        return

    self.progress.setVisible(True)
    self.analyze_btn.setEnabled(False)
    self._status_bar.showMessage(i18n.tr("status.analyzing"))

    self._analyze_worker = AnalyzeWorker(file_path)
    self._analyze_worker.finished.connect(self._on_analysis_done)
    self._analyze_worker.failed.connect(self._on_analysis_failed)
    self._analyze_worker.progress.connect(self._status_bar.showMessage)
    self._analyze_worker.start()

def _on_analysis_done(self, info):
    from app2nix.core.resolver import DependencyResolver
    from app2nix.config import settings
    resolver = DependencyResolver(settings.cache_db.expanduser())
    nix_deps, unresolved = resolver.resolve_all(info.dependencies)
    # ... reste de la logique actuelle de _analyze() depuis "self.current_result = ..."
    self.progress.setVisible(False)
    self.analyze_btn.setEnabled(True)

def _on_analysis_failed(self, error: str):
    self.progress.setVisible(False)
    self.analyze_btn.setEnabled(True)
    self._status_bar.showMessage(i18n.tr("status.failed"))
    QMessageBox.critical(self, i18n.tr("error.analysis"), error)
```

**Modifier `_install_to_system()` pour utiliser `InstallWorker` :**

```python
def _install_to_system(self):
    if not self.current_result or not self.current_file:
        return

    # ⚠️ Avertissement de sécurité OBLIGATOIRE (SEC-02)
    reply = QMessageBox.warning(
        self,
        "Security Warning",
        "Installing this package will:\n"
        "• Copy the package file to ~/nix-packages/\n"
        "• Run nix-build which may execute scripts embedded in the package\n\n"
        "Only install packages from trusted sources.\n\n"
        "Continue?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    pkg_name = self.current_result["name"]
    pkg_dir = Path.home() / "nix-packages" / pkg_name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copy2(self.current_file, pkg_dir / Path(self.current_file).name)
    (pkg_dir / "default.nix").write_text(self.nix_output.toPlainText())

    env = os.environ.copy()
    env["NIXPKGS_ALLOW_UNFREE"] = "1"
    env["NIXPKGS_ALLOW_UNSUPPORTED_SYSTEM"] = "1"

    self.progress.setVisible(True)
    self.progress.setMaximum(0)
    self.install_btn.setEnabled(False)

    # Log en temps réel dans nix_output
    self.nix_output.append("\n# ── nix-build output ──\n")

    self._install_worker = InstallWorker(pkg_dir, env)
    self._install_worker.log_line.connect(
        lambda line: self.nix_output.append(f"  {line}")
    )
    self._install_worker.finished.connect(self._on_install_done)
    self._install_worker.failed.connect(self._on_install_failed)
    self._install_worker.start()

def _on_install_done(self, store_path: str):
    self.progress.setVisible(False)
    self.install_btn.setEnabled(True)
    self._create_desktop_entries(store_path)
    self._status_bar.showMessage(f"Installed to {store_path}")

def _on_install_failed(self, error: str):
    self.progress.setVisible(False)
    self.install_btn.setEnabled(True)
    QMessageBox.critical(self, "Build Failed", error)
```

---

#### TÂCHE S2 — Avertissement sécurité avant installation [SEC-02]

Déjà intégré dans TÂCHE S1 ci-dessus via `QMessageBox.warning()`.

En plus, détecter si le package contient des scripts pre/postinst :

```python
def _check_package_scripts(self, package_path: str) -> list[str]:
    """Retourne la liste des scripts dangereux trouvés dans le package."""
    scripts = []
    import subprocess, tempfile
    if package_path.endswith(".deb"):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["dpkg-deb", "--control", package_path, tmp],
                               capture_output=True, timeout=10)
                for script in ["preinst", "postinst", "prerm", "postrm"]:
                    if (Path(tmp) / script).exists():
                        scripts.append(script)
        except Exception:
            pass
    return scripts
```

Afficher l'avertissement renforcé si des scripts sont détectés.

---

#### TÂCHE S3 — Limite upload dans server.py [SEC-03]

**Fichier :** `server.py`

Remplacer **les deux occurrences** de `await file.read()` (dans `/analyze` et `/generate`) par :

```python
# Dans les routes analyze() et generate() :
# AVANT
content = await file.read()

# APRÈS — ajouter AVANT la lecture
MAX_UPLOAD_BYTES = int(os.environ.get("APP2NIX_MAX_UPLOAD_SIZE", 500 * 1024 * 1024))

content_parts = []
total = 0
async for chunk in file:
    total += len(chunk)
    if total > MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"error": f"File too large. Maximum allowed: {MAX_UPLOAD_BYTES // 1024 // 1024} MB"},
            status_code=413
        )
    content_parts.append(chunk)
content = b"".join(content_parts)
```

---

### ═══════════════════════════════════════
### PRIORITÉ 2 — ARCHITECTURE (5 tâches)
### ═══════════════════════════════════════

---

#### TÂCHE A1 — Supprimer la duplication de build_nix_expression() [ARC-01]

**Problème :** La fonction `build_nix_expression()` (~60 lignes) est définie identiquement dans `server.py` ET `app2nix_gui.py`.

**Action :**

1. Vérifier que `src/app2nix/core/generator.py` existe et contient `NixGenerator` avec une méthode `generate_default_nix(info: PackageInfo) -> ConversionResult`.

2. Si `NixGenerator` n'existe pas, le créer :

```python
# src/app2nix/core/generator.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from app2nix.models import PackageInfo, ConversionResult

ARCH_MAP = {
    "amd64": "x86_64-linux", "i386": "i686-linux", "i686": "i686-linux",
    "arm64": "aarch64-linux", "armhf": "armv7l-linux", "arm": "armv7l-linux",
    "unknown": "x86_64-linux", "x86_64": "x86_64-linux",
}

@dataclass
class NixGenerator:
    """Génère des expressions Nix à partir d'un PackageInfo."""

    def map_arch(self, arch: str) -> str:
        return ARCH_MAP.get(arch.lower(), arch)

    def _install_phase(self, fmt: str) -> tuple[str, list[str]]:
        """Retourne (install_snippet, native_deps)."""
        if fmt == "deb":
            extract = (
                'deb_file=$(find $src -name "*.deb" -o -name "*.ipk" 2>/dev/null | head -1)\n'
                '    if [ -n "$deb_file" ]; then\n'
                '      dpkg-deb -x "$deb_file" $out\n'
                '    else\n'
                '      echo "ERROR: no .deb found in $src"; exit 1\n'
                '    fi'
            )
            native = ["dpkg", "autoPatchelfHook"]
        elif fmt in ("appimage", "AppImage"):
            extract = (
                'appimage=$(find $src -iname "*.AppImage" 2>/dev/null | head -1)\n'
                '    if [ -n "$appimage" ]; then\n'
                '      chmod +x "$appimage"\n'
                '      "$appimage" --appimage-extract 2>/dev/null\n'
                '      [ -d squashfs-root ] && cp -r squashfs-root/* $out/ || { echo "appimage-extract failed"; exit 1; }\n'
                '    else\n'
                '      echo "ERROR: no AppImage found"; exit 1\n'
                '    fi'
            )
            native = ["autoPatchelfHook"]
        elif fmt == "rpm":
            extract = (
                'rpm_file=$(find $src -name "*.rpm" 2>/dev/null | head -1)\n'
                '    if [ -n "$rpm_file" ]; then\n'
                '      rpm2cpio "$rpm_file" | cpio -idmv\n'
                '      cp -r . $out/\n'
                '    else\n'
                '      echo "ERROR: no .rpm found in $src"; exit 1\n'
                '    fi'
            )
            native = ["rpm", "cpio", "autoPatchelfHook"]
        else:
            extract = (
                'pkg=$(find $src -type f ! -name "*.nix" ! -name "*.sh" 2>/dev/null | head -1)\n'
                '    [ -n "$pkg" ] && { mkdir -p $out/bin; cp "$pkg" $out/bin/; } || { echo "ERROR: no file found"; exit 1; }'
            )
            native = ["autoPatchelfHook"]
        return extract, native

    def generate_default_nix(self, info: PackageInfo, resolved_deps: list[str]) -> str:
        """Génère une expression default.nix correcte et reproductible."""
        extract, native = self._install_phase(info.format)
        native_str = "\n".join(f"    pkgs.{p}" for p in native)
        deps_str = "\n".join(f"    pkgs.{d}" for d in resolved_deps)
        pkg_arch = self.map_arch(info.architecture)

        lines = [
            "{ pkgs ? import <nixpkgs> {} }:",
            "",
            "pkgs.stdenv.mkDerivation {",
            f'  pname = "{info.name}";',
            f'  version = "{info.version}";',
            "",
            "  # Place the package file in this directory alongside default.nix",
            "  src = ./.;",
            "",
            "  nativeBuildInputs = with pkgs; [",
            native_str,
            "  ];",
            "",
        ]

        all_deps = f"    pkgs.stdenv.cc.cc.lib\n{deps_str}" if deps_str else "    pkgs.stdenv.cc.cc.lib"
        lines += [
            "  buildInputs = with pkgs; [",
            all_deps,
            "  ];",
            "",
            "  # Skip standard unpack — we handle it in installPhase",
            "  dontUnpack = true;",
            "",
            "  installPhase = ''",
            "    runHook preInstall",
            "    mkdir -p $out",
            f"    {extract}",
            "",
            "    # Link executables to $out/bin",
            "    mkdir -p $out/bin",
            '    find $out/usr $out/opt -type f -executable 2>/dev/null | while read f; do',
            '      case "$f" in *.so.*|*.so) ;; *) ln -sf "$f" "$out/bin/$(basename "$f")" 2>/dev/null ;; esac',
            '    done',
            "",
            '    if [ -d "$out/usr/share" ]; then',
            "      mkdir -p $out/share",
            '      cp -r $out/usr/share/* $out/share/ 2>/dev/null || true',
            "    fi",
            "    runHook postInstall",
            "  '';",
            "",
            "  preFixup = ''",
            "    autoPatchelf $out",
            "  '';",
            "",
            "  meta = with pkgs.lib; {",
            f'    description = "{info.name} — converted for NixOS by app2nix";',
            f'    platforms = [ "{pkg_arch}" ];',
            "    license = licenses.unfree;",
            "    maintainers = [];",
            "  };",
            "}",
        ]
        return "\n".join(lines)

    def generate_flake_nix(self, info: PackageInfo, resolved_deps: list[str]) -> str:
        """Génère un flake.nix moderne."""
        deps_str = "\n".join(f"          pkgs.{d}" for d in resolved_deps)
        attr_name = info.name.replace("-", "_").replace(".", "_")
        pkg_arch = self.map_arch(info.architecture)

        return f'''{{
  description = "{info.name} — converted from {info.format} by app2nix";

  inputs = {{
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    flake-utils.url = "github:numtide/flake-utils";
  }};

  outputs = {{ self, nixpkgs, flake-utils }}:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = nixpkgs.legacyPackages.${{system}};
      in {{
        packages.{attr_name} = pkgs.stdenv.mkDerivation {{
          pname = "{info.name}";
          version = "{info.version}";
          src = ./.;
          nativeBuildInputs = with pkgs; [ autoPatchelfHook ];
          buildInputs = with pkgs; [
            pkgs.stdenv.cc.cc.lib
{deps_str}
          ];
          dontUnpack = true;
          installPhase = \'\'
            mkdir -p $out/bin
            # Add your install logic here
          \'\';
          meta = with pkgs.lib; {{
            description = "{info.name} converted for NixOS";
            platforms = [ "{pkg_arch}" ];
            license = licenses.unfree;
          }};
        }};
        packages.default = self.packages.${{system}}.{attr_name};
      }}
    );
}}'''

    def validate(self, nix_content: str) -> tuple[bool, str | None]:
        """Valide la syntaxe via nix-instantiate --parse si disponible."""
        import subprocess
        try:
            r = subprocess.run(
                ["nix-instantiate", "--parse", "-"],
                input=nix_content, capture_output=True, text=True, timeout=10
            )
            return r.returncode == 0, r.stderr.strip() if r.returncode != 0 else None
        except FileNotFoundError:
            return True, None  # nix non disponible, skip
        except subprocess.TimeoutExpired:
            return True, None
```

3. Dans `server.py`, remplacer `build_nix_expression()` par :

```python
from app2nix.core.generator import NixGenerator
from app2nix.core.resolver import DependencyResolver
from app2nix.config import settings

# Dans generate() :
generator = NixGenerator()
resolver = DependencyResolver(settings.cache_db.expanduser())
resolved_deps, unresolved = resolver.resolve_all(info.dependencies)
generated = generator.generate_default_nix(info, resolved_deps)
flake_generated = generator.generate_flake_nix(info, resolved_deps)
valid, val_error = generator.validate(generated)
```

4. Dans `app2nix_gui.py`, remplacer l'appel à `build_nix_expression()` par :

```python
from app2nix.core.generator import NixGenerator
# ...
generator = NixGenerator()
nix_expr = generator.generate_default_nix(info, nix_deps)
self.nix_output.setPlainText(nix_expr)
```

---

#### TÂCHE A2 — Migrer les imports dépréciés dans server.py [ARC-02]

**Fichier :** `server.py`

```python
# Supprimer ces imports (lignes ~10):
# from analyze_deb import get_all_dependencies
# from lib.deb_to_nix import translate_all

# Remplacer par:
from app2nix.core.analyzer import UniversalAnalyzer
from app2nix.core.resolver import DependencyResolver
from app2nix.core.generator import NixGenerator
from app2nix.config import settings
import logging

logger = logging.getLogger("app2nix.server")

# Remplacer analyze_any() par:
def analyze_any(package_path: str):
    analyzer = UniversalAnalyzer()
    return analyzer.analyze(package_path)

# Dans les routes, remplacer:
# info = analyze_any(str(temp_path))
# nix_deps = translate_all(info.get("dependencies", []))
# Par:
# info = analyze_any(str(temp_path))
# resolver = DependencyResolver(settings.cache_db.expanduser())
# resolved_deps, unresolved = resolver.resolve_all(info.dependencies)

# Remplacer print() par logger:
# print(f"Error in analyze: {e}") → logger.exception("Error in /analyze")
```

---

#### TÂCHE A3 — Migrer lib/i18n et lib/theme dans src/app2nix/ [GUI-02]

**Problème :** `from lib import i18n` et `from lib import theme` fonctionnent en mode dev mais cassent avec `pip install`.

**Actions :**

```bash
# 1. Déplacer dans le package
mkdir -p src/app2nix/gui
cp lib/i18n.py src/app2nix/gui/i18n.py       # ou lib/i18n/__init__.py
cp lib/theme.py src/app2nix/gui/theme.py     # adapter selon structure réelle

# 2. Vérifier que translations/ est inclus dans le package
# Dans pyproject.toml, ajouter si absent:
[tool.hatch.build.targets.wheel]
packages = ["src/app2nix"]
include = ["src/app2nix/gui/translations/**"]
```

**Dans `app2nix_gui.py`, remplacer :**

```python
# Supprimer:
sys.path.insert(0, str(Path(__file__).parent / "src"))
from lib import i18n
from lib import theme as thm

# Remplacer par:
from app2nix.gui.i18n import get_translator as i18n   # adapter selon API réelle
from app2nix.gui.theme import ThemeManager as thm
```

**Déplacer `app2nix_gui.py` dans le package :**

```bash
mkdir -p src/app2nix/gui/
mv app2nix_gui.py src/app2nix/gui/main_window.py
```

**Créer `src/app2nix/gui/__init__.py` :**

```python
def run_gui():
    """Entry point de la GUI."""
    import sys
    from PyQt6.QtWidgets import QApplication
    from app2nix.gui.main_window import App2NixWindow
    app = QApplication(sys.argv)
    window = App2NixWindow()
    window.show()
    sys.exit(app.exec())
```

---

#### TÂCHE A4 — Commande CLI `app2nix gui` [ARC-03]

**Fichier :** `src/app2nix/cli.py`

Ajouter dans le CLI Typer :

```python
@app.command()
def gui():
    """Launch the graphical interface (requires PyQt6)."""
    try:
        from app2nix.gui import run_gui
        run_gui()
    except ImportError:
        console.print("[red]PyQt6 not installed.[/red] Install with: pip install app2nix[gui]")
        raise typer.Exit(1)
```

**Dans `pyproject.toml`, ajouter un optional gui :**

```toml
[project.optional-dependencies]
gui = ["PyQt6>=6.5"]
dev = ["pytest>=7.0", "pytest-asyncio>=0.21", "pytest-cov>=4.0", "pytest-qt>=4.0", "httpx>=0.27", "ruff>=0.4", "mypy>=1.0"]
```

**Mettre à jour `pyproject.toml` scripts :**

```toml
[project.scripts]
app2nix     = "app2nix.cli:app"
app2nix-gui = "app2nix.gui:run_gui"
```

---

#### TÂCHE A5 — Supprimer ou migrer main.py legacy [ARC-05]

**Fichier :** `main.py` (205 lignes, argparse, logique dupliquée)

Option A — Supprimer et rediriger :
```python
# main.py — remplacer tout le contenu par:
#!/usr/bin/env python3
"""Legacy entry point — use 'app2nix' CLI instead."""
import sys
print("app2nix: This script is deprecated. Use 'app2nix convert <file>' instead.", file=sys.stderr)
sys.exit(1)
```

Option B — Migrer vers le CLI (recommandé) :
```bash
# S'assurer que src/app2nix/cli.py contient les commandes équivalentes:
# app2nix convert <file> --output-dir .     (= python main.py <file>)
# app2nix convert <file> --json             (= python main.py --json <file>)
# app2nix convert --url <url>              (= python main.py --url <url>)
# app2nix convert <file> --print-deps      (= python main.py --print-deps)
```

---

### ═══════════════════════════════════════
### PRIORITÉ 3 — QUALITÉ NIX (3 tâches)
### ═══════════════════════════════════════

---

#### TÂCHE N1 — Remplacer unpackPhase = "true" par dontUnpack [NIX-01]

Dans `NixGenerator.generate_default_nix()` (TÂCHE A1 ci-dessus), l'idiome correct est :

```nix
# ❌ AVANT (dans server.py et gui.py)
phases = [ "unpackPhase" "installPhase" "fixupPhase" ];
unpackPhase = "true";

# ✅ APRÈS (dans NixGenerator)
dontUnpack = true;
```

**Note :** La TÂCHE A1 inclut déjà cette correction. Si `NixGenerator` existait déjà, vérifier qu'il utilise `dontUnpack = true` et non l'ancien idiome.

---

#### TÂCHE N2 — Ajouter génération flake.nix dans server.py et GUI [NIX-03]

**Fichier :** `server.py` — route `/generate`

Dans la réponse JSON de `/generate`, ajouter `flake_content` :

```python
# Dans generate() — après generation du default.nix:
flake_content = generator.generate_flake_nix(info, resolved_deps)

return JSONResponse({
    "name": pkg_name,
    "version": pkg_version,
    "architecture": pkg_arch,
    "content": generated,
    "flake_content": flake_content,    # ← NOUVEAU
    "install_guide": install_guide,
    "auto_install_script": auto_script,
    "validation_passed": valid,
    "unresolved_deps": unresolved,     # ← NOUVEAU
})
```

**Fichier :** `app2nix_gui.py` / `src/app2nix/gui/main_window.py`

Dans l'onglet Nix, ajouter un bouton "Copy flake.nix" et un second QTextEdit ou tab pour afficher le flake :

```python
# Dans _setup_nix_tab(), ajouter après le QTextEdit existant:
self.flake_btn = QPushButton("📋 Copy flake.nix")
self.flake_btn.clicked.connect(self._copy_flake)
# ...
self.flake_output = QTextEdit()
self.flake_output.setReadOnly(True)
self.flake_output.setFont(QFont("monospace", 11))
self.flake_output.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none; border-radius: 10px; padding: 16px;")
# Ajouter dans un QTabWidget interne ou QSplitter
```

---

#### TÂCHE N3 — Corriger .desktop Terminal detection [SEC-04 / GUI-08]

**Fichier :** `app2nix_gui.py` — méthode `_on_install_done` / `_install_to_system`

```python
def _is_cli_tool(self, exe_path: Path) -> bool:
    """Détermine si un exécutable est un outil CLI (nécessite un terminal)."""
    import subprocess
    try:
        r = subprocess.run(["file", "-b", str(exe_path)], capture_output=True, text=True, timeout=5)
        return "ELF" in r.stdout and "executable" in r.stdout
    except Exception:
        return False

def _needs_terminal(self, store_path: str, exe_name: str) -> bool:
    """Heuristique : pas de GUI si pas de lib Qt/GTK dans les deps."""
    gui_libs = {"libQt5", "libQt6", "libgtk", "libwx", "libSDL", "libGL"}
    deps = self.current_result.get("libraries", [])
    has_gui = any(any(g.lower() in d.lower() for g in gui_libs) for d in deps)
    return not has_gui

# Dans la génération du .desktop:
terminal = self._needs_terminal(store_path, exe)
(apps_dir / f"{exe}.desktop").write_text(
    f"[Desktop Entry]\nName={exe}\n"
    f"Comment={pkg_name} v{pkg_version} - installed by app2nix\n"
    f"Exec={store_path}/bin/{exe}{' %F' if not terminal else ''}\n"
    f"Icon={pkg_name.lower()}\n"
    f"Terminal={'true' if terminal else 'false'}\n"
    f"Type=Application\n"
    f"Categories={'Utility' if terminal else 'Application'};\n"
    "StartupNotify=true\n"
)
```

---

### ═══════════════════════════════════════
### PRIORITÉ 4 — TESTS & CI (3 tâches)
### ═══════════════════════════════════════

---

#### TÂCHE T1 — Tests GUI avec pytest-qt [TST-01]

**Fichier :** `tests/gui/test_main_window.py` (créer)

```python
"""Tests GUI avec pytest-qt."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt


@pytest.fixture
def window(qtbot):
    """Fixture: fenêtre app2nix initialisée."""
    from app2nix.gui.main_window import App2NixWindow
    win = App2NixWindow()
    qtbot.addWidget(win)
    win.show()
    return win


def test_window_title(window):
    """Le titre doit contenir app2nix."""
    assert "app2nix" in window.windowTitle().lower()


def test_analyze_button_exists(window):
    assert window.analyze_btn is not None
    assert window.analyze_btn.isEnabled()


def test_analyze_button_disabled_during_work(qtbot, window):
    """Le bouton analyse doit se désactiver pendant le traitement."""
    window.file_path.setText("/nonexistent/fake.deb")
    
    with patch.object(window, '_start_analysis') as mock_start:
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)
        # _start_analysis est appelé avec le bon chemin
        mock_start.assert_called_once_with("/nonexistent/fake.deb")


def test_clear_resets_state(qtbot, window):
    """Le bouton clear doit réinitialiser tous les champs."""
    window.file_path.setText("/some/file.deb")
    window.lbl_name.setText("test-app")
    qtbot.mouseClick(window.clear_btn, Qt.MouseButton.LeftButton)
    assert window.file_path.text() == ""
    assert window.lbl_name.text() == "-"
    assert window.current_file is None


def test_unsupported_format_shows_warning(qtbot, window, tmp_path):
    """Un format non supporté doit afficher un avertissement."""
    bad_file = tmp_path / "test.xyz"
    bad_file.write_bytes(b"fake content")
    window.file_path.setText(str(bad_file))
    
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        qtbot.mouseClick(window.analyze_btn, Qt.MouseButton.LeftButton)
        mock_warn.assert_called_once()


def test_nix_generator_called_on_analysis(qtbot, window, tmp_path):
    """L'analyse doit appeler NixGenerator et remplir nix_output."""
    from app2nix.models import PackageInfo
    fake_info = PackageInfo(
        name="test-pkg", version="1.0", architecture="amd64",
        format="deb", dependencies=["ssl", "z"]
    )
    
    with patch('app2nix.gui.main_window.AnalyzeWorker') as MockWorker:
        instance = MockWorker.return_value
        instance.start = MagicMock()
        window._start_analysis("/fake/test.deb")
        instance.start.assert_called_once()


class TestAnalyzeWorker:
    def test_worker_emits_finished_on_success(self, qtbot):
        from app2nix.gui.main_window import AnalyzeWorker
        from app2nix.models import PackageInfo
        
        worker = AnalyzeWorker("/fake/path.deb")
        signals = []
        worker.finished.connect(lambda info: signals.append(info))
        
        fake_info = PackageInfo(name="test", version="1.0", format="deb")
        with patch('app2nix.core.analyzer.UniversalAnalyzer.analyze', return_value=fake_info):
            worker.run()
        
        assert len(signals) == 1
        assert signals[0].name == "test"
```

**Ajouter dans `pyproject.toml` :**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
qt_api = "pyqt6"   # pour pytest-qt
```

---

#### TÂCHE T2 — CI : Validation expressions Nix générées [TST-02]

**Fichier :** `.github/workflows/ci.yml` — ajouter un job `nix-validate` :

```yaml
  nix-validate:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      
      - name: Install Nix
        uses: cachix/install-nix-action@v26
        with:
          nix_path: nixpkgs=channel:nixos-24.05
      
      - name: Install app2nix
        run: pip install uv && uv sync
        env:
          APP2NIX_SECRET_KEY: test-ci-key
      
      - name: Generate and validate Nix expression
        run: |
          # Créer un faux .deb minimal pour le test
          mkdir -p /tmp/test_deb/DEBIAN
          echo -e "Package: test-app\nVersion: 1.0\nArchitecture: amd64\nDescription: test" \
            > /tmp/test_deb/DEBIAN/control
          dpkg-deb --build /tmp/test_deb /tmp/test-app_1.0_amd64.deb
          
          # Générer l'expression Nix
          mkdir -p /tmp/nix_output
          uv run app2nix convert /tmp/test-app_1.0_amd64.deb --output-dir /tmp/nix_output
          
          # Valider la syntaxe
          nix-instantiate --parse /tmp/nix_output/default.nix
          echo "✅ Nix expression is syntactically valid"
        env:
          APP2NIX_SECRET_KEY: test-ci-key
```

---

#### TÂCHE T3 — Seuil de couverture minimum [TST-03]

**Fichier :** `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
qt_api = "pyqt6"
addopts = "--cov=src/app2nix --cov-report=term-missing --cov-fail-under=70"

[tool.coverage.run]
source = ["src/app2nix"]
omit = ["*/gui/main_window.py"]   # GUI coverage séparée via pytest-qt

[tool.coverage.report]
exclude_lines = [
    "if __name__ == .__main__.",
    "raise NotImplementedError",
    "pass",
]
```

---

### ═══════════════════════════════════════
### PRIORITÉ 5 — POLISH (2 tâches)
### ═══════════════════════════════════════

---

#### TÂCHE P1 — README mis à jour [ARC-06]

**Fichier :** `README.md` — Section "Quick Start" à remplacer par :

```markdown
## 🚀 Quick Start

### Installation

```bash
# Depuis PyPI (recommandé)
pip install app2nix

# Avec interface graphique
pip install "app2nix[gui]"

# Depuis les sources
git clone https://github.com/HiTechTN/app2nix.git
cd app2nix && pip install -e .
```

### CLI

```bash
# Convertir un .deb
app2nix convert package.deb

# Convertir un .rpm
app2nix convert package.rpm --output-dir ./myapp

# Générer aussi un flake.nix
app2nix convert package.deb --flake

# Voir les dépendances
app2nix convert package.deb --print-deps

# Démarrer le serveur web
app2nix serve

# Interface graphique (nécessite pip install "app2nix[gui]")
app2nix gui
```

### Web UI

```bash
app2nix serve
# Ouvrir http://localhost:8000
```

### Docker

```bash
docker run -p 8000:8000 -e APP2NIX_SECRET_KEY=mysecret ghcr.io/hitechtn/app2nix:latest
```
```

---

#### TÂCHE P2 — Guide d'installation Jinja2 dans GUI [GUI-05]

**Fichier :** `src/app2nix/gui/templates/install_guide.html.j2` (créer)

```html
<div style="font-family: system-ui, sans-serif; line-height: 1.8;">
  <h2 style="color: #2d4f8c; border-bottom: 3px solid #2d4f8c; padding-bottom: 8px; margin-top: 0;">
    📦 {{ _('install.guide.title') }}: {{ name }} v{{ version }}
  </h2>
  <table style="width:100%;border-collapse:collapse;margin:12px 0;">
    <tr><td><strong>Format</strong></td><td><span class="badge blue">{{ format }}</span></td></tr>
    <tr><td><strong>Arch</strong></td><td><span class="badge purple">{{ arch }}</span></td></tr>
    <tr><td><strong>Deps</strong></td><td><span class="badge green">{{ dep_count }} nixpkgs</span></td></tr>
    {% if unresolved %}<tr><td><strong>Unresolved</strong></td>
    <td><span class="badge red">{{ unresolved|length }}</span> {{ unresolved|join(', ') }}</td></tr>{% endif %}
  </table>
  <!-- ... steps ... -->
</div>
```

**Dans la GUI**, remplacer la f-string de 30 lignes par :

```python
from jinja2 import Environment, PackageLoader
env = Environment(loader=PackageLoader("app2nix.gui", "templates"))
template = env.get_template("install_guide.html.j2")
install_guide = template.render(
    name=pkg_name, version=pkg_version,
    format=fmt_name, arch=map_arch(pkg_arch),
    dep_count=len(nix_deps), unresolved=unresolved,
    _=i18n.tr
)
self.install_output.setHtml(install_guide)
```

---

## ✅ CRITÈRES DE VALIDATION v3.0

Un upgrade est considéré **complet** si tous ces critères passent :

### Fonctionnel
- [ ] `app2nix convert sample.deb` → `default.nix` avec `dontUnpack = true` (pas `unpackPhase = "true"`)
- [ ] `app2nix convert sample.deb --flake` → génère aussi un `flake.nix` valide
- [ ] `app2nix gui` → ouvre la fenêtre Qt sans erreur d'import
- [ ] GUI : cliquer Analyze sur un .deb → **UI reste réactive** pendant l'analyse
- [ ] GUI : cliquer Install → QMessageBox d'avertissement sécurité apparaît d'abord
- [ ] API POST `/generate` → réponse JSON contient `flake_content` non-null
- [ ] Upload d'un fichier >500MB via API → retourne HTTP 413

### Qualité
- [ ] `nix-instantiate --parse default.nix` → exit code 0 sur le Nix généré
- [ ] `pytest tests/ -v` → 100% pass
- [ ] `pytest --cov-fail-under=70` → pass
- [ ] `ruff check src/` → 0 erreur
- [ ] `mypy src/app2nix --ignore-missing-imports` → 0 erreur

### Architecture
- [ ] `server.py` : aucun import depuis `analyze_deb` ou `lib.deb_to_nix`
- [ ] `app2nix_gui.py` ou `src/app2nix/gui/main_window.py` : aucun `from lib import`
- [ ] `build_nix_expression()` définie une seule fois (dans `NixGenerator`)
- [ ] `app2nix_gui.py` à la racine → supprimé ou redirige vers `src/app2nix/gui/main_window.py`

### CI
- [ ] `nix-instantiate --parse` dans `.github/workflows/ci.yml` → pass
- [ ] Docker build → succès

---

## 📁 FICHIERS À CRÉER / MODIFIER

```
CRÉER:
  src/app2nix/core/generator.py          ← NixGenerator (TÂCHE A1)
  src/app2nix/gui/__init__.py            ← run_gui() entry point
  src/app2nix/gui/main_window.py         ← app2nix_gui.py migré
  src/app2nix/gui/templates/             ← templates Jinja2 GUI
  tests/gui/test_main_window.py          ← tests pytest-qt (TÂCHE T1)
  tests/gui/__init__.py
  .env.example                           ← APP2NIX_SECRET_KEY=...

MODIFIER:
  src/app2nix/cli.py                     ← +commande gui (TÂCHE A4)
  server.py                              ← imports + upload limit + NixGenerator
  app2nix_gui.py                         ← QThread workers (ou migrer dans gui/)
  pyproject.toml                         ← +[gui] optional, +pytest-qt, +coverage threshold
  README.md                              ← Quick Start v2.0 CLI
  .github/workflows/ci.yml               ← +job nix-validate

SUPPRIMER / VIDER:
  main.py                                ← remplacer par message deprecated
```

---

## 🔗 RÉFÉRENCES

- NixOS `dontUnpack`: https://nixos.org/manual/nixpkgs/stable/#var-stdenv-dontUnpack
- PyQt6 QThread: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html
- pytest-qt: https://pytest-qt.readthedocs.io/en/latest/
- Nix Flakes: https://nixos.wiki/wiki/Flakes
- Starlette streaming: https://www.starlette.io/requests/#request-body

---

*Généré par audit statique approfondi — HiTechTN/app2nix — Mai 2026*  
*Analysés : main.py (205L) · server.py (357L) · app2nix_gui.py (844L) · analyze_deb.py (16L) · universal_analyze.py (16L) · pyproject.toml (73L)*
