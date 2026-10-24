from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from .versions import application_version_key

ENDED_STATE = 5
DEFAULT_STOP_AFTER = 10

T = TypeVar("T")


class TournamentBridge(Protocol):
    def list_competitions(self, page: int) -> Any: ...

    def competition_page(self, competition_id: int, sub_id: int, page: int) -> Any: ...

    def download_replay(self, replay_path: str) -> Any: ...


@dataclass
class FetchSummary:
    downloaded: int = 0
    present: int = 0
    skipped_version: int = 0
    stop_reason: str = ""
    failed: bool = False


def fetch_replays(
    bridge: TournamentBridge,
    replay_directory: Path,
    versions: Iterable[str],
    stop_after: int | None = DEFAULT_STOP_AFTER,
    log: Callable[[str], None] = lambda _: None,
) -> FetchSummary:
    """Download tournament replays newest first until `stop_after` replays in a row are already on disk,
    or the walk reaches a version older than every requested one.

    `stop_after=None` walks to the version boundary regardless, which resumes an interrupted backfill.
    Replays of versions that were not requested are skipped and do not count toward the streak.
    A failed request is retried once; a second failure stops the run with `failed` set.
    """
    wanted: dict[str, tuple[int, ...]] = {}
    for version in versions:
        key = application_version_key(version)
        if key is None:
            raise ValueError(
                f"invalid version {version!r}; expected the game version and replay format, such as 2.0.0.5.2340."
            )
        wanted[version] = key
    if not wanted:
        raise ValueError("at least one version is required.")
    oldest_version = min(wanted, key=wanted.__getitem__)
    summary = FetchSummary()
    try:
        summary.stop_reason = _walk(bridge, replay_directory, wanted, oldest_version, stop_after, log, summary)
    except Exception as error:
        summary.failed = True
        summary.stop_reason = f"failed after a retry: {error}"
    return summary


def _walk(
    bridge: TournamentBridge,
    replay_directory: Path,
    wanted: dict[str, tuple[int, ...]],
    oldest_version: str,
    stop_after: int | None,
    log: Callable[[str], None],
    summary: FetchSummary,
) -> str:
    streak = 0
    seen: set[str] = set()
    for competition in _competitions(bridge):
        for sub_id in competition.sub_ids:
            for path in _replay_paths(bridge, competition.id, sub_id):
                if path in seen:
                    continue
                seen.add(path)
                version, _, file_name = path.partition("/")
                key = application_version_key(version)
                if key is not None and key < wanted[oldest_version]:
                    return f"reached version {version}, older than {oldest_version}"
                if version not in wanted:
                    summary.skipped_version += 1
                    continue
                downloaded = (
                    not (replay_directory / version / f"{file_name}.grbr").is_file()
                    and _retry(lambda path=path: bridge.download_replay(path)).downloaded
                )
                if downloaded:
                    summary.downloaded += 1
                    streak = 0
                else:
                    summary.present += 1
                    streak += 1
                log(f"{'downloaded' if downloaded else 'present':<11} {path}  (tournament {competition.id}/{sub_id})")
                if stop_after is not None and streak >= stop_after:
                    return f"{stop_after} replays in a row were already downloaded"
    return "no more tournaments"


def _competitions(bridge: TournamentBridge) -> list[Any]:
    """Every listed tournament, newest first. The list is short (a few pages), so it is read up front
    to merge in ended mini tournaments, which the game only reports on the first page."""
    by_id: dict[int, Any] = {}
    page, page_count = 1, 1
    while page <= page_count:
        reply = _retry(lambda page=page: bridge.list_competitions(page))
        page_count = reply.page_count
        for competition in reply.competitions:
            by_id.setdefault(competition.id, competition)
        page += 1
    return sorted(by_id.values(), key=lambda competition: (competition.start_time, competition.id), reverse=True)


def _replay_paths(bridge: TournamentBridge, competition_id: int, sub_id: int) -> Iterator[str]:
    page, page_count = 1, 1
    while page <= page_count:
        reply = _retry(lambda page=page: bridge.competition_page(competition_id, sub_id, page))
        if reply.state != ENDED_STATE:
            return
        page_count = reply.page_count
        yield from reply.replay_paths
        page += 1


def _retry(call: Callable[[], T]) -> T:
    try:
        return call()
    except Exception:
        return call()
