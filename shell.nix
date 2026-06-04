{ pkgs ? import <nixpkgs> {} }:
let
  python-with-packages = pkgs.python3.withPackages (p: with p; [
    # Runtime
    pyqt6
    starlette
    uvicorn
    python-multipart
    pydantic
    pydantic-settings
    itsdangerous
    jinja2
    rich
    typer
    aiosqlite

    # Test
    pytest
    pytest-asyncio
    pytest-qt
    pytest-cov
    httpx
  ]);
in
pkgs.mkShell {
  packages = [
    python-with-packages

    # PyQt6 / Qt6 runtime system libraries
    pkgs.glib          # libglib-2.0 (Glib main loop, IO channels)
    pkgs.libglvnd      # libGL, libGLX, libEGL (OpenGL)
    pkgs.fontconfig    # libfontconfig (font discovery)
    pkgs.libxkbcommon  # libxkbcommon (XKB keyboard handling — Qt6 requirement)
    pkgs.freetype      # libfreetype (font rasterization)
    pkgs.expat         # libexpat (XML parsing)
    pkgs.zlib          # libz (compression)
    pkgs.bzip2         # libbz2 (compression)
    pkgs.libpng        # libpng (PNG image I/O)
    pkgs.harfbuzz      # libharfbuzz (text shaping — ICU + FreeType)
    pkgs.icu           # libicui18n, libicuuc (Unicode — Qt6 requirement)
    pkgs.dbus          # libdbus-1 (inter-process communication)
    pkgs.libxml2       # libxml2 (XML)
    pkgs.pcre2         # libpcre2-8 (regex — used by Glib)
    pkgs.libffi        # libffi (foreign function interface — used by Glib)

            # X11 client libraries (Qt6 XCB platform plugin)
            pkgs.libx11
            pkgs.libxext
            pkgs.libxrender
            pkgs.libxcursor
            pkgs.libxfixes
            pkgs.libxi
            pkgs.libxrandr

    # XCB utilities (Qt6 xcb platform plugin dependencies)
    pkgs.libxcb             # libxcb (core xcb protocol — xcb-randr, xcb-shm, xcb-sync, xcb-xfixes, etc.)
    pkgs.libxcb-cursor      # libxcb-cursor (cursor theme)
    pkgs.libxcb-image       # libxcb-image (X image extension)
    pkgs.libxcb-keysyms     # libxcb-keysyms (key symbols)
    pkgs.libxcb-render-util # libxcb-render-util (render util)
    pkgs.libxcb-util        # libxcb-util (auxiliary — provides libxcb-util.so.1)
    pkgs.libxcb-wm          # libxcb-wm — provides libxcb-icccm.so.4 (inter-client communication)

    # Tools
    pkgs.dpkg
    pkgs.patchelf
    pkgs.file
    pkgs.squashfsTools
    pkgs.xvfb
  ];

  shellHook = ''
    export PYTHONPATH="$PWD/src:$PYTHONPATH"
    echo "🛠️  app2nix dev shell (with PyQt6 GUI test support)"
    echo "   Python: $(python --version)"
    echo ""
    echo "   Run GUI tests: xvfb-run python -m pytest tests/gui/ -v"
    echo "   Run all tests: python -m pytest -v"
    echo ""
  '';
}
