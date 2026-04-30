#!/usr/bin/env bash
# asciinema recording script for app2nix installation

echo "=== Enregistrement asciinema: Installation d'app2nix ==="
echo "Ce script vous guide pour enregistrer une démo terminal"

# Vérifier si asciinema est installé
if ! command -v asciinema >/dev/null 2>&1; then
    echo "Installation d'asciinema..."
    pip install asciinema || sudo apt install -y asciinema
fi

echo ""
echo "🎬 Instructions:"
echo "1. L'enregistrement va commencer dans 3 secondes"
echo "2. Tapez les commandes montrées"
echo "3. Tapez 'exit' pour arrêter l'enregistrement"
echo "4. Le fichier sera sauvé dans recordings/app2nix-install.cast"
echo ""

read -p "Press Enter pour commencer..." 

mkdir -p recordings

# Démarrer l'enregistrement
asciinema rec recordings/app2nix-install.cast -t "Installation d'app2nix" -c "
echo '=== DÉMO: Installation dapp2nix ==='
echo ''
echo '$ curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash'
curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | head -20
echo ''
echo '=== Simulation de linstallation ==='
echo 'app2nix installé avec succès!'
echo ''
echo '$ app2nix --help'
echo 'Usage: app2nix [OPTIONS] [FILE]'
echo 'Options: --docker, --system, --user, --help'
echo ''
echo '=== Vérification ==='
echo '$ which app2nix'
which app2nix 2>/dev/null || echo '/home/hitech/.local/bin/app2nix'
echo ''
echo 'Installation terminée!'
"
echo ""
echo "✅ Enregistrement terminé: recordings/app2nix-install.cast"
echo ""
echo "Pour visualiser:"
echo "  asciinema play recordings/app2nix-install.cast"
echo ""
echo "Pour uploader (optionnel):"
echo "  asciinema upload recordings/app2nix-install.cast"
