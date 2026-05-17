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
pkgs.mkShell {
  packages = [ python-with-packages pkgs.dpkg pkgs.patchelf pkgs.file pkgs.squashfsTools ];
}
