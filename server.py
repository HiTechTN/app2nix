#!/usr/bin/env python3
"""
app2nix - FastAPI Server
"""

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from analyze_deb import get_all_dependencies
from lib.deb_to_nix import translate_all


app = FastAPI(
    title="app2nix API",
    description="Convert .deb packages to NixOS expressions",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORK_DIR = Path(tempfile.mkdtemp(prefix="app2nix_"))

static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


class PackageInfo(BaseModel):
    name: str
    version: str
    architecture: str
    libraries: list[str]
    nix_dependencies: list[str]


class NixOutput(BaseModel):
    name: str
    version: str
    content: str


class DownloadRequest(BaseModel):
    url: str


@app.get("/", response_class=HTMLResponse)
async def root():
    index_file = static_path / "index.html"
    return index_file.read_text()


@app.get("/api")
async def api_root():
    return {"message": "app2nix API", "version": "1.0.0"}


@app.post("/analyze", response_model=PackageInfo)
async def analyze_package(file: UploadFile = File(...)):
    """Analyze a .deb file and return package info."""
    if not file.filename.endswith(".deb"):
        raise HTTPException(status_code=400, detail="File must be .deb")
    
    temp_path = WORK_DIR / file.filename
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    try:
        info = get_all_dependencies(str(temp_path))
        nix_deps = translate_all(info.get("dependencies", []))
        
        return PackageInfo(
            name=info.get("name", "unknown"),
            version=info.get("version", "1.0"),
            architecture=info.get("architecture", "amd64"),
            libraries=info.get("dependencies", []),
            nix_dependencies=nix_deps
        )
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/generate", response_model=NixOutput)
async def generate_nix(file: UploadFile = File(...)):
    """Generate default.nix from .deb file."""
    if not file.filename.endswith(".deb"):
        raise HTTPException(status_code=400, detail="File must be .deb")
    
    temp_path = WORK_DIR / file.filename
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    try:
        info = get_all_dependencies(str(temp_path))
        nix_deps = translate_all(info.get("dependencies", []))
        
        deps_lines = ""
        for dep in nix_deps:
            deps_lines += f"    pkgs.{dep}\n"
        
        content = f'''{{ pkgs ? import <nixpkgs> {{}} }}:

pkgs.stdenv.mkDerivation {{
  pname = "{info.get("name", "app")}";
  version = "{info.get("version", "1.0")}";
  src = ./.;

  nativeBuildInputs = [
    pkgs.autoPatchelfHook
{deps_lines}  ];

  installPhase = ''
    runHook preInstall

    mkdir -p $out/bin
    mkdir -p $out/share

    cp -r usr/share/* $out/share/ 2>/dev/null || true
    cp -r opt/* $out/opt/ 2>/dev/null || true

    runHook postInstall
  '';
}}
'''
        
        return NixOutput(
            name=info.get("name", "app"),
            version=info.get("version", "1.0"),
            content=content
        )
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/download")
async def download_from_url(req: DownloadRequest):
    """Download and analyze .deb from URL."""
    import urllib.request
    
    url = req.url
    filename = url.split("/")[-1]
    if not filename.endswith(".deb"):
        raise HTTPException(status_code=400, detail="URL must point to .deb file")
    
    temp_path = WORK_DIR / filename
    try:
        urllib.request.urlretrieve(url, str(temp_path))
        
        info = get_all_dependencies(str(temp_path))
        nix_deps = translate_all(info.get("dependencies", []))
        
        return {
            "name": info.get("name", "unknown"),
            "version": info.get("version", "1.0"),
            "nix_dependencies": nix_deps
        }
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)