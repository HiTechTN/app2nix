#!/usr/bin/env bash
# Script d'enregistrement vidéo pour app2nix
# Usage: ./scripts/record-video.sh [nom] [duree]

set -e

NAME="${1:-demo}"
DURATION="${2:-30}"
OUTPUT="videos/${NAME}"

mkdir -p videos

echo "🎬 Enregistrement vidéo pour app2nix"
echo "================================"
echo "Nom: $NAME"
echo "Durée: ${DURATION}s"
echo "Output: $OUTPUT"
echo ""
echo "Les commandes seront enregistrées dans un terminal."
echo "Appuyez Ctrl+C pour arrêter."
echo ""

read -p "Appuyez Enter pour commencer l'enregistrement..."

# Démarrer l'enregistrement asciinema
asciinema rec "$OUTPUT.cast" \
    --title "app2nix - $NAME" \
    --cursor \
    --append

echo ""
echo "✅ Enregistrement terminé!"
echo "Fichier: $OUTPUT.cast"
echo ""
echo "Pour visualiser:"
echo "  asciinema play $OUTPUT.cast"
echo ""
echo "Pour convertir en GIF:"
echo "  asciinema gif $OUTPUT.cast > $OUTPUT.gif"
echo ""
echo "Pour convertir en MP4 (nécessite ffmpeg):"
echo "  # d'abord convertir en webm puis en mp4"