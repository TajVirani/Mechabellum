from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from mechabellum.visualizer import Visualizer, VisualizerOptions

FIXTURES = Path(__file__).parent / "fixtures"
LOCAL_PLAYER = "281474976710829150"


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Visualizer]:
    static = tmp_path / "static"
    (static / "vendor").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (static / "app.js").write_text("export {};", encoding="utf-8")
    (static / "vendor" / "lib.mjs").write_text("export {};", encoding="utf-8")
    (static / "style.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    options = VisualizerOptions(
        port=0,
        open_browser=False,
        replay_dir=FIXTURES / "replays",
        data_dir=tmp_path / "data",
        player_id=LOCAL_PLAYER,
        playback=FIXTURES / "live" / "playing-match.sample.jsonl",
        playback_speed=0,
        model=tmp_path / "missing.joblib",
    )
    visualizer = Visualizer(options, static_dir=static)
    visualizer.start()
    assert visualizer.wait_until_indexed(timeout=60)
    assert visualizer.wait_until_live_done(timeout=60)
    yield visualizer
    visualizer.close()


def read_catch_up(url: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    with urllib.request.urlopen(url + "events", timeout=10) as response:
        assert response.headers["Content-Type"].startswith("text/event-stream")
        name = None
        while True:
            line = response.readline().decode("utf-8")
            assert line, "stream ended early"
            if line.startswith("event: "):
                name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                events.append((name, json.loads(line[len("data: ") :])))
                if name == "predictions":
                    return events


def test_bound_to_localhost_only(server: Visualizer) -> None:
    assert server.httpd.server_address[0] == "127.0.0.1"
    assert server.url.startswith("http://127.0.0.1:")


def test_events_send_the_full_catch_up(server: Visualizer) -> None:
    events = read_catch_up(server.url)
    names = [name for name, _ in events]
    # Ten rounds of fight_over history, then the latest frame.
    assert names == ["hello", "summaries", "baseline", "ratings", "status", *["frame"] * 11, "predictions"]
    history = [data["snapshot"]["match"] for name, data in events if name == "frame"][:-1]
    assert [(match["round"], match["phase"]) for match in history] == [
        (number, "fight_over") for number in range(1, 11)
    ]
    data = dict(events)
    assert data["hello"]["localPlayerId"] == LOCAL_PLAYER
    assert data["hello"]["suggestedPlayerId"] == LOCAL_PLAYER
    assert data["hello"]["modelAvailable"] is False
    assert data["hello"]["liveSource"] == "playback"
    assert sorted(row["battleId"] for row in data["summaries"]["rows"]) == [
        "20261022--67509180",
        "20261023--67519030",
        "20261024--67160210",
    ]
    assert list(data["baseline"]["byMode"]) == ["Normal"]
    assert data["baseline"]["byMode"]["Normal"]["byRound"]["1"]["n"] == 3
    assert data["ratings"]["byBattle"]["20261024--67159493"][LOCAL_PLAYER] == 1651
    assert data["status"]["state"] == "playback_done"
    assert data["status"]["indexing"] == {"done": 4, "total": 4}
    assert data["frame"]["localIndex"] == 0
    assert data["frame"]["snapshot"]["match"]["round"] == 10
    assert data["predictions"] == {"battleId": "20261024--67159493", "rows": []}


def test_static_files_and_mime_types(server: Visualizer) -> None:
    expected = {
        "": "text/html",
        "index.html": "text/html",
        "app.js": "text/javascript",
        "vendor/lib.mjs": "text/javascript",
        "style.css": "text/css",
    }
    for path, content_type in expected.items():
        with urllib.request.urlopen(server.url + path, timeout=5) as response:
            assert response.headers["Content-Type"].split(";")[0] == content_type, path
    for path in ("missing.js", "../secret.txt", "%2e%2e/secret.txt"):
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(server.url + path, timeout=5)
        assert error.value.code == 404, path


def test_local_player_api(server: Visualizer, tmp_path: Path) -> None:
    with urllib.request.urlopen(server.url + "api/local-player", timeout=5) as response:
        assert json.load(response)["localPlayerId"] == LOCAL_PLAYER
    request = urllib.request.Request(
        server.url + "api/local-player",
        data=json.dumps({"playerId": "281474976710828382"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.load(response) == {"localPlayerId": "281474976710828382"}
    saved = json.loads((tmp_path / "data" / "visualizer.json").read_text(encoding="utf-8"))
    assert saved == {"localPlayerId": "281474976710828382"}
    data = dict(read_catch_up(server.url))
    assert data["hello"]["localPlayerId"] == "281474976710828382"
    assert data["frame"]["localIndex"] == 1


def test_foreign_host_or_origin_is_refused(server: Visualizer) -> None:
    for headers in ({"Host": "evil.example"}, {"Origin": "http://evil.example"}):
        request = urllib.request.Request(server.url + "api/local-player", headers=headers)
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        assert error.value.code == 403


def test_catalog(server: Visualizer) -> None:
    with urllib.request.urlopen(server.url + "catalog.json", timeout=5) as response:
        assert response.headers["Content-Type"].startswith("application/json")
        catalog = json.load(response)
    assert catalog["roles"] == ["chaff", "chaffClear", "damage", "tank", "support", "unknown"]
    assert catalog["units"]["10"] == {
        "name": "Crawler",
        "primary": "chaff",
        "secondary": None,
        "air": False,
        "hitsAir": False,
        "members": 24,
    }
    assert catalog["units"]["6"]["air"] is True and catalog["units"]["6"]["members"] == 12
    assert len(catalog["units"]) == 33


def test_events_client_gone_before_headers_is_unsubscribed(server: Visualizer) -> None:
    import io

    from mechabellum.visualizer.server import _Handler

    class Gone(io.RawIOBase):
        def write(self, data: bytes) -> int:
            raise ConnectionAbortedError(10053, "aborted")

    handler = _Handler.__new__(_Handler)
    handler.server = server.httpd
    handler.wfile = Gone()
    handler.request_version = "HTTP/1.1"
    handler.requestline = "GET /events HTTP/1.1"
    handler.command = "GET"
    handler.client_address = ("127.0.0.1", 0)
    before = len(server.hub._clients)
    handler._events()
    assert len(server.hub._clients) == before


def test_close_joins_the_worker_threads(tmp_path: Path) -> None:
    options = VisualizerOptions(
        port=0,
        open_browser=False,
        replay_dir=FIXTURES / "replays",
        data_dir=tmp_path / "data",
        playback=FIXTURES / "live" / "playing-match.sample.jsonl",
        playback_speed=0,
        model=tmp_path / "missing.joblib",
    )
    visualizer = Visualizer(options)
    visualizer.start()
    visualizer.close()
    assert visualizer.watcher is not None and visualizer.watcher._thread is not None
    assert not visualizer.watcher._thread.is_alive()
    assert all(not thread.is_alive() for thread in visualizer._threads if thread.name != "http")


def test_serves_before_the_replay_folder_is_indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cold cache doesn't hold up the server: summaries arrive over the stream as they are parsed."""
    import threading

    from mechabellum.visualizer import watcher as watcher_module

    release = threading.Event()
    real = watcher_module.summarize_replay

    def slow(path: Path, root: Path | None = None) -> dict:
        assert release.wait(30)
        return real(path, root)

    monkeypatch.setattr(watcher_module, "summarize_replay", slow)
    options = VisualizerOptions(
        port=0,
        open_browser=False,
        replay_dir=FIXTURES / "replays",
        data_dir=tmp_path / "data",
        live=False,
        model=tmp_path / "missing.joblib",
    )
    visualizer = Visualizer(options)
    try:
        visualizer.start()
        assert not visualizer.wait_until_indexed(timeout=0.2)
        with urllib.request.urlopen(visualizer.url + "events", timeout=10) as response:
            events = []
            name = None
            while len(events) < 5:
                line = response.readline().decode("utf-8")
                if line.startswith("event: "):
                    name = line[len("event: ") :].strip()
                elif line.startswith("data: "):
                    events.append((name, json.loads(line[len("data: ") :])))
            assert [name for name, _ in events] == ["hello", "summaries", "baseline", "ratings", "status"]
            data = dict(events)
            assert data["summaries"]["rows"] == []
            assert data["hello"]["suggestedPlayerId"] is None
            assert data["status"]["indexing"]["done"] == 0
            release.set()
            later: list[tuple[str, dict]] = []
            while not later or later[-1][0] != "status" or later[-1][1]["indexing"]["done"] < 4:
                line = response.readline().decode("utf-8")
                if line.startswith("event: "):
                    name = line[len("event: ") :].strip()
                elif line.startswith("data: "):
                    later.append((name, json.loads(line[len("data: ") :])))
        names = [name for name, _ in later]
        assert "summaries" not in names
        assert names.count("summary") == 3
        assert {"baseline", "status"} <= set(names)
        # The suggested player follows the rows as they arrive.
        configs = [data for name, data in later if name == "config"]
        assert configs and configs[-1] == {"localPlayerId": None, "suggestedPlayerId": LOCAL_PLAYER}
        assert later[-1][1]["indexing"] == {"done": 4, "total": 4}
        assert visualizer.wait_until_indexed(timeout=10)
    finally:
        release.set()
        visualizer.close()
