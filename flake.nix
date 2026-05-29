{
  description = "app2nix - Universal Linux Application Installer for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    rust-overlay.url = "github:oxalica/rust-overlay";
  };

  outputs = { self, nixpkgs, flake-utils, rust-overlay }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        overlays = [ (import rust-overlay) ];
        pkgs = import nixpkgs { inherit system overlays; };
        rustToolchain = pkgs.rust-bin.stable.latest.default.override {
          extensions = [ "rust-src" "rustfmt" "clippy" ];
        };
        nativeBuildInputs = with pkgs; [
          rustToolchain
          pkg-config
        ];
        buildInputs = with pkgs; [
          openssl
        ];
        buildDeps = with pkgs; [
          patchelf
          dpkg
          rpm
          cpio
          squashfsTools
          p7zip
          file
          gawk
        ];

        pythonTestPkgs = with pkgs.python3Packages; [
          pyqt6
          pytest
          pytest-qt
          pytest-cov
          pytest-asyncio
          httpx
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
        ];
      in
      {
        packages.default = pkgs.rustPlatform.buildRustPackage {
          pname = "app2nix";
          version = "3.0.0";
          src = ./.;
          cargoLock = {
            lockFile = ./Cargo.lock;
          };
          nativeBuildInputs = nativeBuildInputs;
          buildInputs = buildInputs;
          buildAndTestSubdir = "crates/cli";
          installPhase = ''
            mkdir -p $out/bin
            cp target/release/app2nix $out/bin/
            mkdir -p $out/share/app2nix/templates
            cp templates/* $out/share/app2nix/templates/
          '';
          meta = with pkgs.lib; {
            description = "Universal Linux application installer for NixOS";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };

        packages.app2nix = self.packages.${system}.default;

        devShells.default = pkgs.mkShell {
          buildInputs = nativeBuildInputs ++ buildInputs ++ buildDeps ++ [
            pkgs.rust-analyzer
          ];

          shellHook = ''
            echo "🛠️  app2nix dev shell"
            echo "   Rust: $(rustc --version)"
            echo "   Tools: patchelf, dpkg, rpm2cpio, unsquashfs, file"
            echo ""
            echo "   Build: cargo build -p app2nix"
            echo "   Run:   cargo run -p app2nix -- --help"
          '';
        };

        devShells.python-tests = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (_: pythonTestPkgs))

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
            pkgs.xorg.libX11       # libX11
            pkgs.xorg.libXext      # libXext (X extensions)
            pkgs.xorg.libXrender   # libXrender (X rendering)
            pkgs.xorg.libXcursor   # libXcursor (cursor themes)
            pkgs.xorg.libXfixes    # libXfixes (X fixes protocol)
            pkgs.xorg.libXi        # libXi (X input extension)
            pkgs.xorg.libXrandr    # libXrandr (X resize, rotate, and reflect)

            # XCB utilities (Qt6 xcb platform plugin dependencies)
            pkgs.libxcb             # libxcb (core xcb protocol — xcb-randr, xcb-shm, xcb-sync, xcb-xfixes, etc.)
            pkgs.libxcb-cursor      # libxcb-cursor (cursor theme)
            pkgs.libxcb-image       # libxcb-image (X image extension)
            pkgs.libxcb-keysyms     # libxcb-keysyms (key symbols)
            pkgs.libxcb-render-util # libxcb-render-util (render util)
            pkgs.libxcb-util        # libxcb-util (auxiliary — provides libxcb-util.so.1)
            pkgs.libxcb-wm          # libxcb-wm — provides libxcb-icccm.so.4 (inter-client communication)

            # Tools
            pkgs.xorg.xvfb       # Xvfb + xvfb-run for headless GUI tests
            pkgs.dpkg
            pkgs.patchelf
            pkgs.file
            pkgs.squashfsTools
          ];

          shellHook = ''
            export PYTHONPATH="$PWD/src:$PYTHONPATH"
            echo "🧪 app2nix Python test shell (with PyQt6 GUI support)"
            echo "   Python: $(python --version)"
            echo "   PyQt6:  $(python -c 'from PyQt6 import QtCore; print(QtCore.PYQT_VERSION_STR)' 2>/dev/null || echo 'not available')"
            echo ""
            echo "   Run GUI tests:  xvfb-run python -m pytest tests/gui/ -v"
            echo "   Run all tests:  python -m pytest --cov=src -v"
            echo ""
          '';
        };

        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/app2nix";
        };

        checks = {
          build = self.packages.${system}.default;
        };
      }
    );
}
