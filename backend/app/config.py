"""Environment-backed paths for the local service; no directories are created on import."""
from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_path: Path = ROOT / "backend/data/caregiving.sqlite3"

    @classmethod
    def from_env(cls):
        value = os.environ.get("CARE_LEARN_DB_PATH")
        return cls(database_path=Path(value).expanduser().resolve()) if value else cls()
