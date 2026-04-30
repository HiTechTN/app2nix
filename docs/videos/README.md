# Guide pour les Vidéos de Support - app2nix

## 🎬 Vidéos à Créer

### 1. **Installation d'app2nix** (2-3 minutes)
**Objectif:** Montrer l'installation simple en une commande

**Plan:**
- Introduction (20 sec): Présentation rapide d'app2nix
- Méthode curl (40 sec): `curl -sL ... | bash`
- Méthode Docker (30 sec): `curl ... | bash -s -- --docker`
- Vérification (20 sec): `app2nix --help`
- Conclusion (10 sec): "C'est fait!"

**Fichiers:**
- Script: `docs/VIDEO_SCRIPTS.md` (section Vidéo 1)
- Enregistrement: `scripts/record-install.sh`
- Présentation: `docs/videos/presentation.html`

---

### 2. **Utilisation de base** (3-4 minutes)
**Objectif:** Montrer l'analyse et la conversion

**Plan:**
- Interface Web (1 min): Glisser-déposer, URL input
- Analyse CLI (1 min): `app2nix package.deb`
- Génération Nix (1 min): Code généré
- Installation NixOS (1 min): Guide automatique

**Fichiers:**
- Script: `docs/VIDEO_SCRIPTS.md` (section Vidéo 2)

---

### 3. **Fonctionnalités Avancées** (3-4 minutes)
**Objectif:** Montrer les cas d'usage complexes

**Plan:**
- Upload URL (45 sec): Téléchargement distant
- Mode serveur (1 min): API REST
- Docker (1 min): Déploiement
- Support communauté (30 sec): GitHub, Issues

**Fichiers:**
- Script: `docs/VIDEO_SCRIPTS.md` (section Vidéo 3)

---

## 🛠️ Outils Recommandés

### Pour l'enregistrement:
1. **asciinema** (Terminal)
   ```bash
   sudo apt install asciinema
   ./scripts/record-install.sh
   ```

2. **OBS Studio** (Écran complet)
   - Télécharger: https://obsproject.com/
   - Setup: 1920x1080, 30 FPS

3. **SimpleScreenRecorder** (Léger)
   ```bash
   sudo apt install simplescreenrecorder
   ```

### Pour la présentation:
- **HTML**: `docs/videos/presentation.html` (ouvrir dans navigateur)
- **PowerPoint**: Utiliser zenskill (si disponible)

---

## 📋 Checklist de Production

### Avant l'enregistrement:
- [ ] Tester l'installation sur machine propre
- [ ] Préparer les fichiers .deb d'exemple
- [ ] Vérifier que l'interface web fonctionne (http://localhost:8000)
- [ ] Préparer les commandes dans un fichier texte
- [ ] Régler la résolution d'écran (1920x1080 min)
- [ ] Fermer les applications non nécessaires
- [ ] Désactiver les notifications

### Pendant l'enregistrement:
- [ ] Parler clairement et lentement
- [ ] Montrer les résultats à l'écran
- [ ] Utiliser des zooms sur les parties importantes
- [ ] Garder les vidéos concises (2-4 min max)

### Après l'enregistrement:
- [ ] Couper les parties inutiles
- [ ] Ajouter des annotations si nécessaire
- [ ] Exporter en MP4 (H.264, AAC)
- [ ] Créer des miniatures attractives
- [ ] Uploader sur YouTube

---

## 🎨 Modèles de Miniatures (Thumbnails)

### Vidéo 1: Installation
- **Fond:** Dégradé bleu foncé (#0F172A)
- **Texte:** "app2nix - Installation en 2 min"
- **Élément visuel:** Terminal avec commande curl

### Vidéo 2: Utilisation
- **Fond:** Blanc (#FFFFFF)
- **Texte:** "Convertir .deb → NixOS"
- **Élément visuel:** Icône de conversion

### Vidéo 3: Avancé
- **Fond:** Bleu clair (#3B82F6)
- **Texte:** "Fonctionnalités Avancées"
- **Élément visuel:** Code Nix

---

## 📝 Descriptions YouTube

Voir les modèles complets dans `docs/VIDEO_SCRIPTS.md` (section "Modèles de descriptions YouTube")

**Points clés à inclure:**
- Lien GitHub: https://github.com/HiTechTN/app2nix
- Démo en ligne: http://hitechtn.github.io/app2nix/
- Commande d'installation rapide
- Hashtags: #app2nix #nixos #linux #tutorial

---

## 🔗 Liens Utiles

- **Documentation NixOS:** https://nixos.org/manual/nixos/stable/
- **Recherche de packages:** https://search.nixos.org/packages
- **Forum NixOS:** https://discourse.nixos.org/
- **app2nix GitHub:** https://github.com/HiTechTN/app2nix
- **Demo en ligne:** http://hitechtn.github.io/app2nix/

---

## 📧 Contact

Pour toute question sur les vidéos:
- **Email:** azmi.hitech@gmail.com
- **GitHub Issues:** https://github.com/HiTechTN/app2nix/issues
