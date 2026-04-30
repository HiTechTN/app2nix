#!/usr/bin/env bash
# asciinema recording script for app2nix usage

echo "=== Enregistrement asciinema: Utilisation d'app2nix ==="

mkdir -p recordings

asciinema rec recordings/app2nix-usage.cast -t "Utilisation d'app2nix - Convertir .deb en Nix" -c "
echo '=== DÉMO: Utilisation dapp2nix ==='
echo ''
echo '1. Analyse dun package .deb'
echo '$ app2nix package.deb'
echo ''
echo 'Simulation:'
echo '{'
echo '  \"name\": \"hello\",'
echo '  \"version\": \"2.10\",'
echo '  \"dependencies\": [\"libc6\", \"gcc\"],'
echo '  \"nix_dependencies\": [\"glibc\", \"gcc\"]'
echo '}'
echo ''
echo '2. Génération de lexpression Nix'
echo '$ app2nix --generate package.deb'
echo ''
echo 'Simulation:'
echo '{ pkgs ? import <nixpkgs> {} }:'
echo ''
echo 'pkgs.stdenv.mkDerivation {'
echo '  pname = \"hello\";'
echo '  version = \"2.10\";'
echo '  ...'
echo '}'
echo ''
echo '3. Interface Web'
echo '$ app2nix-server &'
echo 'Opening http://localhost:8000'
echo ''
echo '4. Installation automatique sur NixOS'
echo '$ curl -sL https://raw.githubusercontent.com/HiTechTN/app2nix/master/install.sh | bash'
echo ''
echo '=== Démo terminée ==='
"
echo ""
echo "✅ Enregistrement terminé: recordings/app2nix-usage.cast"
