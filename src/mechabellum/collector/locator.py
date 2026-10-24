from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GameLocations:
    install_directory: Path | None
    replay_directory: Path | None
    player_log: Path | None


def locate_game() -> GameLocations:
    install = _locate_from_running_process() or _locate_from_steam()
    replay = install / "ProjectDatas" / "Replay" if install else None
    home = Path.home()
    player_log = home / "AppData" / "LocalLow" / "GameRiver" / "Mechabellum" / "Player.log"
    return GameLocations(
        install if install and install.is_dir() else None,
        replay if replay and replay.is_dir() else None,
        player_log if player_log.is_file() else None,
    )


def replay_files(replay_directory: Path) -> list[Path]:
    """Every replay under the replay directory, in a stable order: the matches the game saves at the top level and
    the downloaded ones (the in-game download button, `mecha fetch-replays`) in one folder per application version."""
    paths = replay_directory.rglob("*.grbr")
    return sorted(paths, key=lambda path: path.relative_to(replay_directory).as_posix().casefold())


def _locate_from_running_process() -> Path | None:
    if os.name != "nt":
        return None
    try:
        from .memory.windows_process import find_module, find_process_id

        process_id = find_process_id("Mechabellum.exe")
        if process_id is None:
            return None
        module = find_module(process_id, "Mechabellum.exe")
        return module.path.parent if module else None
    except Exception:
        return None


def _locate_from_steam() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam_path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except (OSError, ValueError):
        return None

    libraries = [steam_path]
    library_file = steam_path / "steamapps" / "libraryfolders.vdf"
    if library_file.is_file():
        text = library_file.read_text(encoding="utf-8", errors="ignore")
        libraries.extend(Path(value.replace("\\\\", "\\")) for value in re.findall(r'"path"\s+"([^"]+)"', text))
    for library in libraries:
        install = library / "steamapps" / "common" / "Mechabellum"
        if install.is_dir():
            return install
    return None
