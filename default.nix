{ pkgs ? import <nixpkgs> {} }:

let
  python-with-packages = pkgs.python3.withPackages (p: with p; [
    starlette
    uvicorn
    python-multipart
    httpx
    pydantic
    pydantic-settings
    jinja2
    typer
    rich
    aiosqlite
    itsdangerous
  ]);
in
pkgs.stdenv.mkDerivation {
  pname = "app2nix";
  version = "3.0.1";

  src = ./.;

  nativeBuildInputs = [ python-with-packages pkgs.makeWrapper pkgs.dpkg pkgs.patchelf pkgs.file ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/python3/site-packages
    cp -r $src/src/app2nix $out/lib/python3/site-packages/app2nix

    makeWrapper ${python-with-packages}/bin/python $out/bin/app2nix \
      --add-flags "-m" \
      --add-flags "app2nix" \
      --set PYTHONPATH "$out/lib/python3/site-packages" \
      --prefix PATH : ${pkgs.dpkg}/bin \
      --prefix PATH : ${pkgs.patchelf}/bin \
      --prefix PATH : ${pkgs.file}/bin

    makeWrapper ${python-with-packages}/bin/python $out/bin/app2nix-server \
      --add-flags "-m" \
      --add-flags "app2nix" \
      --add-flags "serve" \
      --set PYTHONPATH "$out/lib/python3/site-packages"

    makeWrapper ${python-with-packages}/bin/python $out/bin/app2nix-gui \
      --add-flags "-m" \
      --add-flags "app2nix.gui" \
      --set PYTHONPATH "$out/lib/python3/site-packages"
  '';

  meta = with pkgs.lib; {
    description = "Convert Linux packages to NixOS expressions";
    homepage = "https://github.com/HiTechTN/app2nix";
    license = licenses.mit;
    platforms = platforms.linux;
  };
}
