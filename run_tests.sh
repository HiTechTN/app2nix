#!/usr/bin/env bash
set -e

echo "=== Building LD_LIBRARY_PATH ==="

# Known Nix store paths (discovered earlier)
GLIB="/nix/store/0iksbi3kkh2af1jv5zzf7jx1f0rxh201-glib-2.86.3/lib"
LIBGLVND="/nix/store/208r91rq2yr19cxqldvj8qf47bcvrxmq-libglvnd-1.7.0/lib"
LIBXKB="/nix/store/6dd6hb49bbkxkqyig6l8wm9wk7dwdzgg-libxkbcommon-1.11.0/lib"
FREETYPE="/nix/store/c3f2kwrbgbr21c7m7k2v7i6vzkf854ha-freetype-2.13.3/lib"
EXPAT="/nix/store/dn34cing3fxa7j6pi29xrfxp2nrb0i3y-expat-2.7.5/lib"
ZLIB="/nix/store/lf793zr9yfa0dpph8jlxbbdnvnahvq8b-zlib-1.3.2/lib"
VENV_QT=".venv/lib/python3.11/site-packages/PyQt6/Qt6/lib"

# Find fontconfig lib (multi-output package)
FC_LIB=$(ls -d /nix/store/*fontconfig*lib 2>/dev/null | grep -v dev | head -1)/lib || echo ""
echo "  fontconfig lib: $FC_LIB"

# Find other multi-output package libs
HARFBUZZ_LIB=$(ls -d /nix/store/*harfbuzz*lib 2>/dev/null | grep -v dev | head -1)/lib || echo ""
ICU_LIB=$(ls -d /nix/store/*icu*lib 2>/dev/null | grep -v dev | head -1)/lib || echo ""
DBUS_LIB=$(ls -d /nix/store/*dbus*lib 2>/dev/null | grep -v dev | head -1)/lib || echo ""
LIBPNG_LIB=$(ls -d /nix/store/*libpng*lib 2>/dev/null | grep -v dev | head -1)/lib || echo ""

# Build full library path
LIBS="$GLIB:$LIBGLVND:$LIBXKB:$FREETYPE:$EXPAT:$ZLIB:$VENV_QT"
[ -d "$FC_LIB" ] && LIBS="$LIBS:$FC_LIB"
[ -d "$HARFBUZZ_LIB" ] && LIBS="$LIBS:$HARFBUZZ_LIB"
[ -d "$ICU_LIB" ] && LIBS="$LIBS:$ICU_LIB"
[ -d "$DBUS_LIB" ] && LIBS="$LIBS:$DBUS_LIB"
[ -d "$LIBPNG_LIB" ] && LIBS="$LIBS:$LIBPNG_LIB"

export LD_LIBRARY_PATH="$LIBS"
export PYTHONPATH="$PWD/src:$PYTHONPATH"

echo "LD_LIBRARY_PATH entries: $(echo $LD_LIBRARY_PATH | tr ':' '\n' | wc -l)"
echo ""

echo "=== Running full test suite ==="
.venv/bin/python -m pytest -v --tb=short -q --cov=src/app2nix --cov-report=term-missing
