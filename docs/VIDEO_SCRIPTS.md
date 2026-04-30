# Scripts de Vidéos de Support - app2nix

## Vidéo 1: Installation d'app2nix (2-3 minutes)

### Introduction (0:00 - 0:20)
**Texte:** "Bonjour! Dans cette vidéo, nous allons installer app2nix, l'outil qui convertit n'importe quel package Linux en application native NixOS."

**Actions:**
- Afficher le logo app2nix
- Montrer la page GitHub: https://github.com/HiTechTN/app2nix

### Méthode 1: Installation Rapide avec curl (0:20 - 1:00)
**Texte:** "La méthode la plus simple est d'utiliser la commande curl."

**Actions:**
```bash
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash
```

**Points à montrer:**
- La bannière s'affiche
- L'installation automatique des dépendances
- Le message "Installation complete!"

### Méthode 2: Avec Docker (1:00 - 1:40)
**Texte:** "Si vous préférez Docker, utilisez l'option --docker"

**Actions:**
```bash
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash -s -- --docker
```

**Points à montrer:**
- L'image Docker se télécharge
- Le container démarre
- Accès à http://localhost:8000

### Vérification (1:40 - 2:00)
**Actions:**
```bash
app2nix --help
which app2nix
app2nix --version
```

### Conclusion (2:00 - 2:30)
**Texte:** "Félicitations! app2nix est maintenant installé. Passons à l'utilisation!"

---

## Vidéo 2: Utilisation de base (3-4 minutes)

### Interface Web (0:00 - 1:00)
**Actions:**
1. Ouvrir http://localhost:8000
2. Montrer l'interface moderne
3. Glisser-déposer un fichier .deb

**Texte:** "L'interface web permet d'analyser et convertir vos packages facilement."

### Analyse d'un package (1:00 - 2:00)
**Actions:**
```bash
# Exemple avec un vrai package
wget http://archive.ubuntu.com/ubuntu/pool/main/h/hello/hello_2.10-3build1_amd64.deb
app2nix hello_2.10-3build1_amd64.deb
```

**Montrer:**
- Les dépendances détectées
- Les équivalents Nix
- Le code Nix généré

### Installation sur NixOS (2:00 - 3:30)
**Texte:** "Voici où app2nix brille vraiment - l'installation automatique sur NixOS!"

**Actions:**
1. Copier le guide d'installation généré
2. Créer le fichier default.nix
3. Lancer la commande d'installation automatique

```bash
# Commande générée par app2nix
nix-env -i -f default.nix
```

### Conclusion (3:30 - 4:00)
**Texte:** "Avec app2nix, convertir des packages Linux vers NixOS n'a jamais été aussi simple!"

---

## Vidéo 3: Fonctionnalités Avancées (3-4 minutes)

### Upload par URL (0:00 - 1:00)
**Actions:**
1. Cliquer sur "Download & Analyze"
2. Entrer une URL de package .deb
3. Montrer l'analyse automatique

### Mode CLI avancé (1:00 - 2:30)
**Actions:**
```bash
# Analyser un package
app2nix package.deb

# Générer l'expression Nix
app2nix-server &
curl -X POST -F "file=@package.deb" http://localhost:8000/generate
```

### Docker et déploiement (2:30 - 3:30)
**Actions:**
```bash
# Démarrer avec Docker
docker run -p 8000:8000 ghcr.io/hitechtn/app2nix:master

# Vérifier sur GitHub Container Registry
docker pull ghcr.io/hitechtn/app2nix:master
```

### Support et communauté (3:30 - 4:00)
**Montrer:**
- GitHub Issues
- Documentation en ligne
- Forum NixOS

---

## Conseils pour l'enregistrement

### Outils recommandés:
1. **asciinema** - Pour les enregistrements terminal
   ```bash
   sudo apt install asciinema
   asciinema rec -t "app2nix Installation"
   ```

2. **OBS Studio** - Pour l'enregistrement d'écran complet
3. **SimpleScreenRecorder** - Alternative Linux légère

### Setup recommandé:
- Résolution: 1920x1080 minimum
- Police: Monospace 14pt minimum
- Thème terminal: Sombre (Solarized Dark)
- Supprimer les fichiers sensibles de l'écran

### Structure type:
1. Hook (5-10 sec) - Problème que résout l'outil
2. Demo (60%) - Montrer l'outil en action
3. Call-to-action (10 sec) - GitHub, étoile, fork

---

## Modèles de descriptions YouTube

### Vidéo 1:
**Titre:** "Comment installer app2nix en 2 minutes - Convertisseur Linux vers NixOS"

**Description:**
```
🚀 app2nix - L'outil qui manquait à NixOS!

Dans cette vidéo, découvrez comment installer app2nix, l'outil révolutionnaire qui convertit n'importe quel package Linux (.deb, .rpm, AppImage) en application native NixOS.

📦 Liens utiles:
- GitHub: https://github.com/HiTechTN/app2nix
- Documentation: http://hitechtn.github.io/app2nix/
- Docker: ghcr.io/hitechtn/app2nix:master

⚡ Installation rapide:
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash

#app2nix #nixos #linux #packaging #tutorial
```

### Vidéo 2:
**Titre:** "Convertir un .deb en package NixOS native - Tutoriel complet"

**Description:**
```
📦 Transformez n'importe quel package Linux en application NixOS native!

Apprenez à utiliser app2nix pour:
✅ Analyser les dépendances
✅ Générer les expressions Nix
✅ Installer automatiquement sur NixOS
✅ Utiliser l'interface web moderne

🎯 Parfait pour les débutants en NixOS!

🔗 Essayer en ligne: http://hitechtn.github.io/app2nix/
🔗 GitHub: https://github.com/HiTechTN/app2nix

#nixos #linux #tutorial #app2nix #devops
```
