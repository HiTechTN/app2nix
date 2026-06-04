{ pkgs ? import <nixpkgs> {} }:

let
  python-with-packages = pkgs.python3.withPackages (p: with p; [
    pyqt6
    starlette
    uvicorn
    python-multipart
    httpx
    pydantic
    pydantic-settings
    jinja2
    typer
    rich
    itsdangerous
  ]);
in
pkgs.stdenv.mkDerivation {
  pname = "app2nix-gui";
  version = "3.1.0";
  src = ./.;
  dontUnpack = true;
  buildInputs = [ python-with-packages pkgs.makeWrapper pkgs.squashfsTools pkgs.rpm pkgs.cpio pkgs.dpkg pkgs.patchelf pkgs.file ];
  installPhase = ''
    mkdir -p $out/bin $out/lib/python3/site-packages
    cp -r $src/src/app2nix $out/lib/python3/site-packages/app2nix

    makeWrapper ${python-with-packages}/bin/python $out/bin/app2nix-gui \
      --add-flags "-m" \
      --add-flags "app2nix.gui" \
      --set PYTHONPATH "$out/lib/python3/site-packages" \
      --prefix PATH : ${pkgs.squashfsTools}/bin \
      --prefix PATH : ${pkgs.rpm}/bin \
      --prefix PATH : ${pkgs.cpio}/bin \
      --prefix PATH : ${pkgs.dpkg}/bin \
      --prefix PATH : ${pkgs.patchelf}/bin \
      --prefix PATH : ${pkgs.file}/bin

    makeWrapper ${python-with-packages}/bin/python $out/bin/app2nix \
      --add-flags "-m" \
      --add-flags "app2nix" \
      --set PYTHONPATH "$out/lib/python3/site-packages" \
      --prefix PATH : ${pkgs.squashfsTools}/bin \
      --prefix PATH : ${pkgs.rpm}/bin \
      --prefix PATH : ${pkgs.cpio}/bin \
      --prefix PATH : ${pkgs.dpkg}/bin \
      --prefix PATH : ${pkgs.patchelf}/bin \
      --prefix PATH : ${pkgs.file}/bin

    makeWrapper ${python-with-packages}/bin/python $out/bin/app2nix-server \
      --add-flags "-m" \
      --add-flags "app2nix" \
      --add-flags "serve" \
      --set PYTHONPATH "$out/lib/python3/site-packages" \
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
