from pathlib import Path

import pytest

pytest.importorskip("google.protobuf")

from mechabellum.bridge import BridgeClient, BridgeError  # noqa: E402
from mechabellum.bridge import bridge_pb2 as pb  # noqa: E402
from mechabellum.collector.tournament import fetch_replays  # noqa: E402

CURRENT = "2.0.0.5.2340"
PREVIOUS = "2.0.0.4.2331"
OLDER = "2.0.0.1.2324"


class FakeBridge:
    """Serves tournaments as {competition_id: (start_time, {sub_id: [page of replay paths, ...]})}."""

    def __init__(self, tournaments: dict, page_size: int = 20, failures: dict | None = None) -> None:
        self.tournaments = tournaments
        self.page_size = page_size
        self.failures = dict(failures or {})
        self.downloads: list[str] = []
        self.states: dict[tuple[int, int], int] = {}

    def _maybe_fail(self, key: object) -> None:
        if self.failures.get(key, 0) > 0:
            self.failures[key] -= 1
            raise BridgeError("timeout", f"simulated failure for {key}")

    def list_competitions(self, page: int) -> pb.ListCompetitionsReply:
        items = sorted(self.tournaments.items(), key=lambda item: item[1][0], reverse=True)
        pages = [items[at : at + self.page_size] for at in range(0, len(items), self.page_size)] or [[]]
        competitions = [
            pb.Competition(id=competition_id, start_time=start, sub_ids=list(subs))
            for competition_id, (start, subs) in pages[page - 1]
        ]
        return pb.ListCompetitionsReply(page=page, page_count=len(pages), competitions=competitions)

    def competition_page(self, competition_id: int, sub_id: int, page: int) -> pb.CompetitionPageReply:
        self._maybe_fail(("page", competition_id, sub_id, page))
        pages = self.tournaments[competition_id][1][sub_id]
        return pb.CompetitionPageReply(
            competition_id=competition_id,
            sub_id=sub_id,
            page=page,
            page_count=len(pages),
            state=self.states.get((competition_id, sub_id), 5),
            replay_paths=pages[page - 1],
        )

    def download_replay(self, replay_path: str) -> pb.DownloadReplayReply:
        self._maybe_fail(replay_path)
        self.downloads.append(replay_path)
        return pb.DownloadReplayReply(replay_path=replay_path, file_path=f"x/{replay_path}.grbr", downloaded=True)


def _paths(version: str, start: int, count: int) -> list[str]:
    return [f"{version}/{number}.rep" for number in range(start, start + count)]


def _store(directory: Path, paths: list[str]) -> None:
    for path in paths:
        target = directory / f"{path}.grbr"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")


def test_downloads_newest_first_and_stops_after_ten_present(tmp_path: Path) -> None:
    newest = _paths(CURRENT, 100, 5)
    have = _paths(CURRENT, 200, 12)
    never = _paths(CURRENT, 300, 3)
    _store(tmp_path, have)
    bridge = FakeBridge({3: (30, {1: [newest]}), 2: (20, {1: [have[:6], have[6:]]}), 1: (10, {1: [never]})})

    summary = fetch_replays(bridge, tmp_path, [CURRENT])

    assert bridge.downloads == newest
    assert (summary.downloaded, summary.present, summary.failed) == (5, 10, False)
    assert "10 replays in a row" in summary.stop_reason


def test_full_walks_past_downloaded_replays_to_the_version_boundary(tmp_path: Path) -> None:
    have = _paths(CURRENT, 100, 30)
    missing = _paths(CURRENT, 200, 2)
    older = _paths(PREVIOUS, 300, 2)
    _store(tmp_path, have)
    bridge = FakeBridge({3: (30, {1: [have]}), 2: (20, {1: [missing]}), 1: (10, {1: [older]})})

    summary = fetch_replays(bridge, tmp_path, [CURRENT], stop_after=None)

    assert bridge.downloads == missing
    assert summary.present == 30
    assert summary.stop_reason == f"reached version {PREVIOUS}, older than {CURRENT}"


def test_a_new_replay_resets_the_streak(tmp_path: Path) -> None:
    have = _paths(CURRENT, 100, 15)
    _store(tmp_path, have[:9] + have[10:])
    bridge = FakeBridge({1: (10, {1: [have]})})

    summary = fetch_replays(bridge, tmp_path, [CURRENT])

    assert bridge.downloads == [have[9]]
    assert summary.present == 14
    assert summary.stop_reason == "no more tournaments"


def test_newer_versions_are_skipped_and_older_versions_stop(tmp_path: Path) -> None:
    current = _paths(CURRENT, 100, 30)
    previous = _paths(PREVIOUS, 200, 2)
    older = _paths(OLDER, 300, 2)
    bridge = FakeBridge({3: (30, {1: [current]}), 2: (20, {1: [previous]}), 1: (10, {1: [older]})})

    summary = fetch_replays(bridge, tmp_path, [PREVIOUS])

    assert bridge.downloads == previous
    assert summary.skipped_version == 30
    assert summary.stop_reason == f"reached version {OLDER}, older than {PREVIOUS}"


def test_several_versions_skip_the_ones_in_between(tmp_path: Path) -> None:
    current = _paths(CURRENT, 100, 1)
    previous = _paths(PREVIOUS, 200, 3)
    older = _paths(OLDER, 300, 2)
    bridge = FakeBridge({3: (30, {1: [current]}), 2: (20, {1: [previous]}), 1: (10, {1: [older]})})

    summary = fetch_replays(bridge, tmp_path, [CURRENT, OLDER])

    assert bridge.downloads == current + older
    assert summary.skipped_version == 3


def test_walks_every_sub_bracket_and_page_and_dedupes_shared_replays(tmp_path: Path) -> None:
    shared = f"{CURRENT}/1.rep"
    bridge = FakeBridge({1: (10, {1: [[shared, f"{CURRENT}/2.rep"], [shared]], 2: [[f"{CURRENT}/3.rep"]]})})

    fetch_replays(bridge, tmp_path, [CURRENT])

    assert bridge.downloads == [shared, f"{CURRENT}/2.rep", f"{CURRENT}/3.rep"]


def test_unfinished_brackets_are_skipped(tmp_path: Path) -> None:
    bridge = FakeBridge({2: (20, {1: [[f"{CURRENT}/1.rep"]]}), 1: (10, {1: [[f"{CURRENT}/2.rep"]]})})
    bridge.states[(2, 1)] = 1

    fetch_replays(bridge, tmp_path, [CURRENT])

    assert bridge.downloads == [f"{CURRENT}/2.rep"]


def test_tournaments_from_every_list_page_are_sorted_newest_first(tmp_path: Path) -> None:
    bridge = FakeBridge({number: (number, {1: [[f"{CURRENT}/{number}.rep"]]}) for number in range(1, 6)}, page_size=2)

    fetch_replays(bridge, tmp_path, [CURRENT])

    assert bridge.downloads == [f"{CURRENT}/{number}.rep" for number in range(5, 0, -1)]


def test_a_failure_is_retried_once(tmp_path: Path) -> None:
    paths = _paths(CURRENT, 100, 2)
    bridge = FakeBridge({1: (10, {1: [paths]})}, failures={paths[0]: 1, ("page", 1, 1, 1): 1})

    summary = fetch_replays(bridge, tmp_path, [CURRENT])

    assert bridge.downloads == paths
    assert not summary.failed


def test_a_second_failure_stops_the_run(tmp_path: Path) -> None:
    paths = _paths(CURRENT, 100, 3)
    bridge = FakeBridge({1: (10, {1: [paths]})}, failures={paths[1]: 2})

    summary = fetch_replays(bridge, tmp_path, [CURRENT])

    assert bridge.downloads == paths[:1]
    assert summary.failed
    assert "simulated failure" in summary.stop_reason


def test_invalid_versions_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        fetch_replays(FakeBridge({}), tmp_path, ["latest"])
    # A game version without the replay format would match no server path.
    with pytest.raises(ValueError):
        fetch_replays(FakeBridge({}), tmp_path, ["2.0.0.5"])


class FakeConnection:
    def __init__(self, replies: list) -> None:
        self.sent: list[pb.Envelope] = []
        self.replies = replies

    def send(self, data: bytes) -> None:
        self.sent.append(pb.Envelope.FromString(data))

    def recv(self, timeout: float) -> bytes:
        reply = self.replies.pop(0)
        return reply(self.sent[-1].id).SerializeToString()


def test_client_ignores_events_and_matches_replies_by_id() -> None:
    event = lambda _: pb.Envelope(id=0)  # noqa: E731
    stale = lambda request_id: pb.Envelope(id=request_id + 100, status_reply=pb.StatusReply())  # noqa: E731
    reply = lambda request_id: pb.Envelope(id=request_id, status_reply=pb.StatusReply(game_version=CURRENT))  # noqa: E731
    connection = FakeConnection([event, stale, reply])

    status = BridgeClient(connection).status()

    assert status.game_version == CURRENT
    assert connection.sent[0].WhichOneof("body") == "status_request"


def test_client_raises_bridge_errors() -> None:
    error = lambda request_id: pb.Envelope(id=request_id, error=pb.Error(code="not_online", message="offline"))  # noqa: E731

    with pytest.raises(BridgeError) as raised:
        BridgeClient(FakeConnection([error])).download_replay(f"{CURRENT}/1.rep")

    assert raised.value.code == "not_online"
