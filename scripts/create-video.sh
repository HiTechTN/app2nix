#!/usr/bin/env bash
# Script de création de vidéo pour app2nix
# Usage: ./scripts/create-video.sh
# Créé un fichier de commandes pour enregistrer

set -e
cd "$(dirname "$0")/.."
mkdir -p videos

echo "🎬 Création de vidéo app2nix"
echo "========================="

# Demander le type de vidéo
echo ""
echo "Quel type de vidéo voulez-vous créer?" echo "  1. Installation d'app2nix"
echo "  2. Utilisation de base" echo "  3. Fonctionnalités avancées"
echo "  4. Animation du processus" echo ""
read -p "Votre choix [1-4]: " CHOICE

case $CHOICE in
    1) VIDEO_TYPE="installation" TITLE="Installation d'app2nix en 2 minutes" ;;
    2) VIDEO_TYPE="utilisation" TITLE="Conversion d'un package en NixOS" ;;
    3) VIDEO_TYPE="avancee" TITLE="Fonctionnalités avancées d'app2nix" ;;
    *) echo "Choix invalide"; exit 1 ;;
esac

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT="videos/${VIDEO_TYPE}_${TIMESTAMP}"

echo ""
echo "📹 Configuration:"
echo "  Type: $VIDEO_TYPE"
echo "  Titre: $TITLE" echo "  Output: $OUTPUT"
echo ""

# Créer le fichier de commandes
cat > "${OUTPUT}_commands.sh" << 'SCRIPT'
#!/usr/bin/env bash
# Commandes pour la vidéo: TITLE
# Ouvrez ce fichier dans un terminal et exécutez les commandes une par une

# Titre de la vidéo
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  app2nix - TITLE" echo "═══════════════════════════════════════════════════════════"
echo ""

# Commandes à exécuter
SCRIPT

chmod +x "${OUTPUT}_commands.sh"
echo "✅ Fichier créé: ${OUTPUT}_commands.sh"
echo ""
echo "Prochaine étape:"
echo "  1. Ouvrez OBS Studio: obs" echo "  2. Configurez l'enregistrement d'écran"
echo "  3. Exécutez: ./videos/${VIDEO_TYPE}_${TIMESTAMP}_commands.sh" echo "  4. Enregistrez les commandes"
echo "  5. Arrêtez OBS et sauvegardez en MP4"