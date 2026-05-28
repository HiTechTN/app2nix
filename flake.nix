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
