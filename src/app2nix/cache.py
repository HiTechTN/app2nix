import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


class DepCache:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS resolved (
                    lib_name TEXT PRIMARY KEY,
                    nixpkg TEXT,
                    source TEXT,
                    confidence REAL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS cache_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def get(self, lib_name: str) -> tuple[str, str, float] | None:
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT nixpkg, source, confidence FROM resolved WHERE lib_name = ?",
                (lib_name,),
            ).fetchone()
            if row:
                return row[0], row[1], row[2]
        return None

    def set(self, lib_name: str, nixpkg: str, source: str, confidence: float):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT OR REPLACE INTO resolved (lib_name, nixpkg, source, confidence) VALUES (?, ?, ?, ?)",
                (lib_name, nixpkg, source, confidence),
            )

    def clear_expired(self, ttl_days: int = 30):
        cutoff = datetime.now() - timedelta(days=ttl_days)
        with sqlite3.connect(self.db_path) as db:
            db.execute("DELETE FROM resolved WHERE cached_at < ?", (cutoff.isoformat(),))
