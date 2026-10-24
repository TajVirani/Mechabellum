"""Game version strings, shared by the live memory reader, the replay parser and tournament fetching.

The game's `Application.version` is "<game version>.<replay format>", for example "2.0.0.5.2340". The game version
("2.0.0.5") is what MatchSnapshot `gameVersion` and the memory layouts carry; the replay format (2340) is the `Version`
a replay records and MatchSnapshot `replayVersion`. The game names its folders of downloaded replays and the server's
replay paths after the full string, and the MechaBridge mod reports it as `StatusReply.game_version`.
"""

from __future__ import annotations


def application_version(game_version: str, replay_format: int) -> str:
    return f"{game_version}.{replay_format}"


def split_application_version(text: str) -> tuple[str, int] | None:
    """(game version, replay format), or None when `text` is not "<four-part game version>.<replay format>"."""
    parts = text.strip().split(".")
    if len(parts) < 5 or not all(parts) or not parts[-1].isdigit():
        return None
    return ".".join(parts[:-1]), int(parts[-1])


def application_version_key(text: str) -> tuple[int, ...] | None:
    """A sort key for an all-numeric application version such as 2.0.0.5.2340, else None."""
    if split_application_version(text) is None:
        return None
    try:
        return tuple(int(part) for part in text.strip().split("."))
    except ValueError:
        return None
