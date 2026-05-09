# Fonctionnement d'app2nix

## Architecture generale

app2nix est un convertisseur de paquets Linux (`.deb`, `.rpm`, `.AppImage`, `.tar.gz`, `.flatpak`, `.snap`) en **derivations Nix** pour NixOS. Il se compose de trois interfaces :

```
                    +-----------+
 Utilisateur -----> |  CLI      | -----+
                    +-----------+      |
                                       v
                    +-----------+  +--------+  +------------+
 Utilisateur -----> |  Web UI   |->| Server |->| Analyseur  |
                    +-----------+  +--------+  +------------+
                                       |            |
                                       v            v
                    +-----------+  +--------+  +------------+
 Utilisateur -----> |  API      |->| Gen.   |->| Mapping    |
                    +-----------+  | Nix    |  | Deb->Nix   |
                                   +--------+  +------------+
                                       |
                                       v
                                 +------------+
                                 | Expression |
                                 | Nix        |
                                 +------------+
```

### Composants principaux

| Composant | Role |
|-----------|------|
| `server.py` | Serveur web Starlette. Points d'entree API : `/analyze`, `/generate`. Sert l'interface utilisateur. |
| `analyze_deb.py` | Analyse approfondie des paquets `.deb` : extraction, detection des binaires ELF, dependances dynamiques. |
| `universal_analyze.py` | Analyse multi-format : `.deb`, `.rpm`, `.AppImage`, `.tar.gz`, `.flatpak`, `.snap`. |
| `lib/deb_to_nix.py` | Dictionnaire de mapping : noms de bibliotheques Debian -> noms de paquets Nixpkgs (150+ entrees). |
| `main.py` | Interface en ligne de commande (CLI). |
| `static/index.html` | Interface web monopage (SPA) avec convertisseur integre. |
| `templates/default.nix` | Template d'expression Nix avec placeholders. |

---

## Pipeline de conversion

Le processus de conversion se deroule en **6 etapes** :

```
  1. Upload/Telechargement
  2. Extraction
  3. Analyse des dependances
  4. Traduction Deb -> Nix
  5. Generation de l'expression Nix
  6. Livraison (JSON + Guide + Script)
```

### Etape 1 : Reception du paquet

Le serveur accepte le fichier via :
- **Upload direct** : multipart/form-data (champ `file`)
- **URL distante** : telechargement via `urllib.request` (champ `url`)

Le format est valide via `get_format()` qui verifie l'extension contre la liste `SUPPORTED_FORMATS`.

### Etape 2 : Analyse

#### Pour les paquets `.deb`

La fonction `get_all_dependencies()` dans `analyze_deb.py` :

1. **Extraction** : `dpkg-deb -x` extrait le contenu dans un dossier temporaire
2. **Recherche de binaires** : `find_executables()` parcourt l'arborescence et identifie les ELF via `file -b`
3. **Detection des bibliotheques** :
   - `get_library_dependencies()` : utilise `ldd` sur chaque binaire ELF
   - `get_patchelf_dependencies()` : utilise `patchelf --print-needed` pour les dependances directes
4. **Lecture des metadonnees** :
   - Primaire : fichier `DEBIAN/control` extrait (contient Package, Version, Architecture, Depends)
   - Fallback : `dpkg-deb -I` (en-tete du paquet)

#### Pour les AppImage

1. `chmod +x` rend le fichier executable
2. `--appimage-extract` extrait le contenu dans `squashfs-root/`
3. Parcours recursif des fichiers ELF avec `patchelf --print-needed`
4. Les noms de bibliotheques sont extraits (suppression du prefixe `lib` et suffixe `.so`)

#### Pour les autres formats (rpm, tar.gz, flatpak, snap)

Actuellement, l'analyse se base sur le nom du fichier et renvoie un jeu minimal d'informations. L'analyse approfondie via `universal_analyze.py` est disponible separement.

### Etape 3 : Traduction Deb -> Nix

`lib/deb_to_nix.py` contient un dictionnaire de mapping `LIBRARY_MAP` qui traduit les noms courts de bibliotheques (ex: `gtk-3`, `ssl`, `z`) en noms de paquets Nixpkgs (ex: `gtk3`, `openssl`, `zlib`).

Categories couvertes :
- Graphisme : `libdrm`, `mesa`, `gtk3`, `cairo`, `freetype`
- Systeme : `expat`, `dbus`, `glib`, `nss`, `nspr`
- Compression : `zlib`, `zstd`, `bzip2`, `xz`
- Chiffrement : `libgcrypt`, `openssl`, `gnutls`
- OpenGL : `mesa`, `glu`, `freeglut`, `glew`
- X11/Wayland : `libX11`, `xcb-util`, `wayland`
- Audio : `alsa-lib`, `libpulse`, `jack2`, `opus`
- FFmpeg : `ffmpeg`
- Qt5 : `qt5.qtbase`, `qt5.qtwebengine`
- Images : `libpng`, `libjpeg`, `libwebp`
- Reseau : `curl`, `libssh`, `openldap`
- Python : `python311`, `python312`
- GStreamer : `gstreamer`, `gst-plugins-base`
- Polices : `harfbuzz`, `icu`
- Securite : `libseccomp`, `apparmor`

### Etape 4 : Generation de l'expression Nix

`build_nix_expression()` dans `server.py` construit une derivation Nix complete :

```nix
{ pkgs ? import <nixpkgs> {} }:

let
  pname = "nom-du-paquet";
  version = "1.0.0";
in pkgs.stdenv.mkDerivation {
  inherit pname version;
  src = ./.;                               # Repertoire contenant le .deb
  
  nativeBuildInputs = with pkgs; [
    pkgs.dpkg                               # Pour extraire le .deb
    pkgs.autoPatchelfHook                   # Correction automatique des ELF
  ];
  
  buildInputs = with pkgs; [                # Dependances detectees
    pkgs.gtk3
    pkgs.openssl
    ...
  ];
  
  phases = [ "unpackPhase" "installPhase" "fixupPhase" ];
  unpackPhase = "true";
  
  installPhase = ''
    mkdir -p $out
    deb_file=$(find $src -name "*.deb" | head -1)
    dpkg-deb -x "$deb_file" $out
    
    # Creation des liens symboliques dans $out/bin
    mkdir -p $out/bin
    for dir in $out/usr/bin $out/usr/local/bin $out/opt/*/bin; do
      ...
    done
  '';
  
  preFixup = ''
    autoPatchelf $out
  '';
  
  meta = with pkgs.lib; {
    platforms = [ "x86_64-linux" ];
    license = licenses.unfree;
  };
}
```

Details par format :

| Format | Methode d'extraction | Outils necessaires |
|--------|---------------------|-------------------|
| `.deb` | `dpkg-deb -x` | `dpkg` |
| `.AppImage` | `--appimage-extract` | `autoPatchelfHook` |
| `.rpm` | `cp` direct | `autoPatchelfHook` |
| `.tar.gz` | `cp` direct | `autoPatchelfHook` |
| `.flatpak` | `cp` direct | `autoPatchelfHook` |
| `.snap` | `cp` direct | `autoPatchelfHook` |

### Etape 5 : Mapping d'architecture

Les architectures Debian sont converties en plateformes Nix via `ARCH_MAP` :

| Debian | Nix |
|--------|-----|
| `amd64` | `x86_64-linux` |
| `i386` | `i686-linux` |
| `arm64` | `aarch64-linux` |
| `armhf` | `armv7l-linux` |

### Etape 6 : Livraison

La reponse JSON contient trois elements :
- **`content`** : L'expression Nix complete
- **`install_guide`** : Guide d'installation en Markdown (etapes 1 a 4)
- **`auto_install_script`** : Script shell autonome pour installation en une commande

---

## Interface Web

L'interface utilisateur est une **application monopage** (SPA) en HTML/CSS/JS avec Bootstrap 5.

### Sections

| Section | Contenu |
|---------|---------|
| **Hero** | Banniere avec animation de particules, boutons CTA |
| **Features** | 6 cartes : conversion 1-clic, auto-dependances, support universel, interface web, CLI + API, Auto-PatchELF |
| **Formats** | Logos des 6 formats supportes |
| **Converter** | Zone de depot, barre d'etape, terminal de log, carte de resultat avec 3 onglets |
| **Docs** | Documentation API avec exemples curl, documentation CLI |
| **Footer** | Liens produit, ressources, communaute |

### Fonctionnalites du convertisseur

- **Barre API URL** : connexion a une instance distante
- **Zone de depot** : glisser-deposer ou cliquer pour selectionner un fichier
- **Barre de progression** : 6 etapes animees avec chronometre
- **Terminal** : logs horodates du processus
- **Statistiques** : nombre de dependances, temps de conversion, taille du paquet
- **Onglets de resultat** : Expression Nix / Guide d'installation / Script automatique
- **Boutons d'action** : Copier, Telecharger, Copier commande d'installation

---

## API REST

### `POST /analyze`
Analyse un paquet et retourne ses metadonnees et dependances.

```bash
curl -F "file=@package.deb" http://localhost:8000/analyze
```

Reponse :
```json
{
  "name": "mon-app",
  "version": "1.0.0",
  "format": "deb",
  "architecture": "x86_64-linux",
  "libraries": ["gtk-3", "ssl", "cairo"],
  "nix_dependencies": ["gtk3", "openssl", "cairo"]
}
```

### `POST /generate`
Analyse ET genere l'expression Nix complete.

```bash
curl -F "file=@package.deb" http://localhost:8000/generate
```

Reponse :
```json
{
  "name": "mon-app",
  "version": "1.0.0",
  "architecture": "x86_64-linux",
  "content": "{ pkgs ? import <nixpkgs> {} }: ...",
  "install_guide": "# Guide d'installation NixOS ...",
  "auto_install_script": "#!/usr/bin/env bash ..."
}
```

---

## Installation du paquet converti sur NixOS

Une fois l'expression Nix generee, l'installation se fait en 4 etapes :

```bash
# 1. Preparer le repertoire
mkdir -p ~/nix-packages/mon-app
cd ~/nix-packages/mon-app

# 2. Copier le paquet source dans ce repertoire

# 3. Creer default.nix (coller l'expression generee)
cat > default.nix << 'EOF'
{ pkgs ? import <nixpkgs> {} }: ...
EOF

# 4. Installer
NIXPKGS_ALLOW_UNFREE=1 NIXPKGS_ALLOW_UNSUPPORTED_SYSTEM=1 nix-env -i -f default.nix
```

Pour une installation systeme, ajouter dans `/etc/nixos/configuration.nix` :
```nix
environment.systemPackages = with pkgs; [
  (callPackage ~/nix-packages/mon-app {})
];
```

---

## Formats supportes

| Format | Extension | Analyse approfondie | Extraction |
|--------|-----------|-------------------|------------|
| Debian | `.deb` | Oui (ldd + patchelf + control) | `dpkg-deb -x` |
| RPM | `.rpm` | Partielle | Copie directe |
| AppImage | `.AppImage`, `.appimage` | Oui (patchelf) | `--appimage-extract` |
| Archive | `.tar.gz`, `.tgz` | Partielle | Copie directe |
| Flatpak | `.flatpak` | Partielle | Copie directe |
| Snap | `.snap` | Partielle | Copie directe |

---

## Technologies utilisees

| Technologie | Usage |
|-------------|-------|
| **Python 3.11+** | Langage serveur |
| **Starlette** | Framework web asynchrone |
| **Uvicorn** | Serveur ASGI |
| **Bootstrap 5** | Interface utilisateur |
| **Docker** | Conteneurisation |
| **dpkg** | Extraction des paquets .deb |
| **patchelf** | Detection des dependances ELF |
| **file** | Identification des types de fichiers |
| **Nixpkgs** | Catalogue de paquets cible |

---

## Flux de donnees complet

```
                     Fichier paquet
                          |
                          v
              +---------------------+
              |   server.py         |
              |   POST /analyze     |
              |   POST /generate    |
              +---------------------+
                 |              |
                 v              v
        +----------+     +------------+
        | Analyse   |     | Detection  |
        | metadonnees|    | dependances|
        +----------+     +------------+
              |              |
              v              v
        +----------+     +------------+
        | Nom,     |     | libgtk-3   |
        | Version, |     | libssl     |
        | Arch     |     | libcairo   |
        +----------+     +------------+
              |              |
              v              v
        +-----------------------------+
        | lib/deb_to_nix.py           |
        | Traduction Deb -> Nix       |
        +-----------------------------+
              |
              v
        +-----------------------------+
        | build_nix_expression()      |
        | Generation de la derivation |
        +-----------------------------+
              |
              v
        +-----------------------------+
        | Reponse JSON                |
        | - content (expression Nix)  |
        | - install_guide             |
        | - auto_install_script       |
        +-----------------------------+
              |
              v
        +-----------------------------+
        | Installation sur NixOS      |
        | nix-env -i -f default.nix   |
        +-----------------------------+
```
