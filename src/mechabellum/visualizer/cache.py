"""The Visualizer's data directory: `visualizer.sqlite` (summaries and captured ratings) and `visualizer.json`."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .summaries import SUMMARY_CACHE_KEY

DATABASE_NAME = "visualizer.sqlite"
CONFIG_NAME = "visualizer.json"


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "mechabellum-analytics"


@dataclass(frozen=True)
class CachedSummary:
    # None when the replay was skipped (not 1v1, no winner, or unreadable).
    summary: dict[str, Any] | None
    skipped_reason: str | None


class SummaryCache:
    """sqlite cache of Match Summaries keyed by (path, size, mtime, SUMMARY_CACHE_KEY), plus pre-match ratings."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS summaries (path TEXT PRIMARY KEY, size INTEGER NOT NULL, "
                "mtime_ns INTEGER NOT NULL, version INTEGER NOT NULL, summary TEXT, skipped_reason TEXT)"
            )
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS ratings (battle_id TEXT NOT NULL, player_id TEXT NOT NULL, "
                "rating INTEGER NOT NULL, PRIMARY KEY (battle_id, player_id))"
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def lookup(self, path: Path, size: int, mtime_ns: int) -> CachedSummary | None:
        """The cached entry for this exact file state, or None when it must be (re)parsed."""
        with self._lock:
            row = self._db.execute(
                "SELECT size, mtime_ns, version, summary, skipped_reason FROM summaries WHERE path = ?",
                (str(path),),
            ).fetchone()
        if row is None or (row[0], row[1], row[2]) != (size, mtime_ns, SUMMARY_CACHE_KEY):
            return None
        return CachedSummary(None if row[3] is None else json.loads(row[3]), row[4])

    def store(self, path: Path, size: int, mtime_ns: int, entry: CachedSummary) -> None:
        summary = None if entry.summary is None else json.dumps(entry.summary, ensure_ascii=False)
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO summaries VALUES (?, ?, ?, ?, ?, ?)",
                (str(path), size, mtime_ns, SUMMARY_CACHE_KEY, summary, entry.skipped_reason),
            )

    def forget(self, path: Path) -> None:
        """Drop the cached entry of a replay that no longer exists."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM summaries WHERE path = ?", (str(path),))

    def store_rating(self, battle_id: str, player_id: str, rating: int) -> bool:
        """Keep the first rating seen for (battle, player) as its pre-match rating; True when it was new."""
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO ratings VALUES (?, ?, ?)", (battle_id, player_id, int(rating))
            )
            return cursor.rowcount > 0

    def ratings(self) -> dict[str, dict[str, int]]:
        with self._lock:
            rows = self._db.execute("SELECT battle_id, player_id, rating FROM ratings ORDER BY battle_id").fetchall()
        by_battle: dict[str, dict[str, int]] = {}
        for battle_id, player_id, rating in rows:
            by_battle.setdefault(battle_id, {})[player_id] = rating
        return by_battle


class VisualizerConfig:
    """`visualizer.json`: the Local Player id."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        value = data.get("localPlayerId") if isinstance(data, dict) else None
        self._local_player_id: str | None = str(value) if value else None

    @property
    def local_player_id(self) -> str | None:
        return self._local_player_id

    def set_local_player_id(self, player_id: str | None) -> None:
        with self._lock:
            self._local_player_id = player_id
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps({"localPlayerId": player_id}, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self._path)
