{ pkgs ? import <nixpkgs> {} }:

let
  python-with-packages = pkgs.python3.withPackages (p: with p; [
    pyqt6
    starlette
    uvicorn
    python-multipart
    pydantic
    itsdangerous
  ]);
in
pkgs.stdenv.mkDerivation {
  pname = "app2nix-gui";
  version = "1.0.0";
  src = ./.;
  dontUnpack = true;
  buildInputs = [ python-with-packages pkgs.makeWrapper pkgs.squashfsTools pkgs.rpm pkgs.cpio pkgs.dpkg pkgs.patchelf pkgs.file ];
  installPhase = ''
    mkdir -p $out/bin $out/lib/app2nix
    cp $src/*.py $out/lib/app2nix/
    cp $src/lib $out/lib/app2nix/ -r
    cp $src/translations $out/lib/app2nix/ -r
    makeWrapper ${python-with-packages}/bin/python $out/bin/app2nix-gui \
      --add-flags "$out/lib/app2nix/app2nix_gui.py" \
      --chdir "$out/lib/app2nix" \
      --prefix PATH : ${pkgs.squashfsTools}/bin \
      --prefix PATH : ${pkgs.rpm}/bin \
      --prefix PATH : ${pkgs.cpio}/bin \
      --prefix PATH : ${pkgs.dpkg}/bin \
      --prefix PATH : ${pkgs.patchelf}/bin \
      --prefix PATH : ${pkgs.file}/bin
  '';
  meta = {
    description = "Universal Package to NixOS Converter";
    homepage = "https://github.com/HiTechTN/app2nix";
    platforms = pkgs.lib.platforms.linux;
  };
}
