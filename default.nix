{ pkgs ? import <nixpkgs> {} }:

let
  app2nix = pkgs.stdenv.mkDerivation {
    pname = "app2nix";
    version = "1.0.0";
    
    src = pkgs.fetchFromGitHub {
      owner = "HiTechTN";
      repo = "app2nix";
      rev = "master";
      sha256 = "sha256-...";
    };
    
    nativeBuildInputs = with pkgs; [
      python3
      python3Packages.pip
      dpkg
      patchelf
      file
    ];
    
    buildInputs = with pkgs; [
      python3Packages.fastapi
      python3Packages.uvicorn
      python3Packages.pydantic
      python3Packages.python-multipart
    ];
    
    installPhase = ''
      mkdir -p $out/bin
      mkdir -p $out/lib/python3.11/site-packages
      
      cp -r * $out/lib/python3.11/site-packages/
      
      makeWrapper $out/bin/app2nix $out/bin/app2nix \
        --set PYTHONPATH "$out/lib/python3.11/site-packages"
      
      makeWrapper $out/bin/app2nix-server $out/bin/app2nix-server \
        --set PYTHONPATH "$out/lib/python3.11/site-packages"
    '';
    
    meta = with pkgs; {
      description = "Convert Linux packages to NixOS expressions";
      homepage = "https://github.com/HiTechTN/app2nix";
      license = licenses.mit;
      platforms = platforms.linux;
    };
  };
in
  app2nix