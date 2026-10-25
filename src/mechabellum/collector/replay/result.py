from __future__ import annotations

import json
from pathlib import Path

RESULT_SUFFIX = ".result.json"


def result_path(replay_path: Path) -> Path:
    """`<id>.rep.grbr` → `<id>.rep.result.json`, next to the replay."""
    return replay_path.with_name(replay_path.name.removesuffix(".grbr") + RESULT_SUFFIX)


def write_result(replay_path: Path, winner_user_id: int, loser_user_id: int, source: str) -> None:
    """Record who won a replay whose file does not say, such as a tournament replay downloaded from the server."""
    payload = {"winner_user_id": str(winner_user_id), "loser_user_id": str(loser_user_id), "source": source}
    result_path(replay_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_winner_user_id(replay_path: Path) -> str | None:
    path = result_path(replay_path)
    if not path.is_file():
        return None
    winner = json.loads(path.read_text(encoding="utf-8")).get("winner_user_id")
    return winner if winner and winner != "0" else None
