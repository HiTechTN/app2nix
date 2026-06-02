import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PackageFormat = Literal["deb", "rpm", "appimage", "flatpak", "snap", "tarball", "unknown"]

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9._-]")

class PackageInfo(BaseModel):
    name: str
    version: str = "1.0"
    architecture: str = "x86_64"
    format: PackageFormat = "unknown"
    dependencies: list[str] = Field(default_factory=list)
    executables: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _SANITIZE_RE.sub("-", v).lower()

class ResolvedDependency(BaseModel):
    original: str
    nixpkg: str | None = None
    confidence: float = 0.0
    source: Literal["dict", "api", "fuzzy", "unknown"] = "unknown"

class ConversionResult(BaseModel):
    package: PackageInfo
    nix_content: str
    flake_content: str | None = None
    install_script: str = ""
    install_guide: str = ""
    resolved_deps: list[ResolvedDependency] = Field(default_factory=list)
    unresolved_deps: list[str] = Field(default_factory=list)
    validation_passed: bool = True
    validation_error: str | None = None

