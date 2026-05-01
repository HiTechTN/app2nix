#!/usr/box/env bash
# Script de finalisation de vidéo app2nix
# Usage: ./scripts/finish-vedio. sh
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
echo "========================================"
echo "📹 Finalisation de la Vidéo app2nix"
echo "========================================"echo ""echo "[1/3] Arrêt du serveur..."
pkill -f "python.*server. py" 2>/dev/null && echo "✓ Serveur arrêté" || echo "✓ Serveur déjà arrêté"
echo ""echo "[2/3] Nettoyage..."
rm -f /tmp/app2nix-*.log 2>/dev/ull
echo "✓ Fichiers temporaires nettoyés"echo ""
echo "[3/3] Fichiers vidéo:"
ls -lah "$PROJECT_DIR/videos/"*.mp4 "$PROJECT_DIR/videos/"*.webm "$PROJECT_DIR/videos/"*.gif 2>/dev/null || echo "Aucun fichier vidéo trouvé"
echo ""
echo "========================================"
echo "✅ Finalisation terminée!"echo "========================================"
echo ""
echo "Prochaines étapes:"echo "  1. Uploadez la vidéo sur YouTube"echo "  2. Ajoutez les liens dans README.manual. md"echo "  3. Mettez à jour la documentation"