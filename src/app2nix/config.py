from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str
    debug: bool = False
    max_upload_size: int = 500 * 1024 * 1024
    upload_timeout: int = 60
    work_dir: Path = Path("/tmp/app2nix")
    api_rate_limit: int = 10
    cache_db: Path = Path("~/.cache/app2nix/deps.db")
    cache_ttl_days: int = 30
    validate_nix: bool = True
    nix_timeout: int = 10

    model_config = {"env_file": ".env", "env_prefix": "APP2NIX_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
