"""Fixtures for the Visualizer's end-to-end tests: `mecha visualize` subprocesses and a headless installed Chrome.

Everything here skips cleanly when Playwright or Chrome is missing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
LOCAL_PLAYER = "281474976710829150"
LOCAL_NAME = "Sleep Deprived"
OPPONENT_NAME = "AllTheFunUsernamesAreTaken"
BATTLE_ID = "20261024--67159493"
START_TIMEOUT = 60.0
# The model stack loads in the background (~15 s) before the playback starts.
PLAYBACK_TIMEOUT = 150.0


@dataclass
class Server:
    url: str
    process: subprocess.Popen[str]
    stderr_path: Path

    def stderr(self) -> str:
        try:
            return self.stderr_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


@dataclass
class Tab:
    """A page plus everything it logged: console errors, page errors and every request URL."""

    page: Any
    errors: list[str] = field(default_factory=list)
    requests: list[str] = field(default_factory=list)

    def foreign_requests(self) -> list[str]:
        return [
            url
            for url in self.requests
            if urlsplit(url).scheme not in ("data", "blob", "about") and urlsplit(url).hostname != "127.0.0.1"
        ]

    def assert_clean(self) -> None:
        assert self.errors == [], f"console errors: {self.errors}"
        assert self.foreign_requests() == [], f"requests left 127.0.0.1: {self.foreign_requests()}"


def start_server(data_dir: Path, player_id: str | None = None) -> Server:
    data_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "mechabellum.cli",
        "visualize",
        "--no-browser",
        "--port",
        "0",
        "--data-dir",
        str(data_dir),
        "--replay-dir",
        str(FIXTURES / "replays"),
        "--playback",
        str(FIXTURES / "live" / "playing-match.sample.jsonl"),
        "--playback-speed",
        "0",
    ]
    if player_id:
        command += ["--player-id", player_id]
    stderr_path = data_dir / "stderr.txt"
    stderr = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    stderr.close()
    found: list[str] = []
    ready = threading.Event()

    def read() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if line.startswith("Visualizer: ") and not found:
                found.append(line.split(" ", 1)[1].strip())
                ready.set()
        ready.set()

    threading.Thread(target=read, daemon=True).start()
    ready.wait(START_TIMEOUT)
    if not found:
        stop_server(process)
        raise RuntimeError(f"mecha visualize did not print its URL:\n{stderr_path.read_text(encoding='utf-8')}")
    return Server(found[0], process, stderr_path)


def stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(10)


def catch_up(url: str) -> list[tuple[str, Any]]:
    """The `/events` catch-up: every event up to and including `status` (and the frames after it, if quick)."""
    events: list[tuple[str, Any]] = []
    with urllib.request.urlopen(url + "events", timeout=10) as stream:
        name = None
        while True:
            line = stream.readline().decode("utf-8")
            if not line:
                break
            line = line.rstrip("\n")
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: ") and name:
                events.append((name, json.loads(line[len("data: ") :])))
                if name == "status":
                    break
    return events


def wait_for_playback(server: Server, timeout: float = PLAYBACK_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert server.process.poll() is None, f"server exited:\n{server.stderr()}"
        status = dict(catch_up(server.url)).get("status") or {}
        if status.get("state") == "playback_done":
            return
        time.sleep(0.5)
    raise AssertionError(f"playback did not finish in {timeout} s:\n{server.stderr()}")


def open_tab(browser: Any, url: str, *, width: int = 1280, height: int = 900) -> Tab:
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    tab = Tab(page)
    page.on("console", lambda message: tab.errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: tab.errors.append(f"pageerror: {error}"))
    page.on("request", lambda request: tab.requests.append(request.url))
    page.goto(url)
    page.wait_for_function("() => window.__visualizer && window.__visualizer.store.hello.get()", timeout=20_000)
    # The server indexes the replay folder in the background; the Stats checks want the finished set.
    page.wait_for_function(
        """() => {
          const ix = window.__visualizer.store.status.get()?.indexing;
          return ix && ix.total != null && ix.done >= ix.total;
        }""",
        timeout=START_TIMEOUT * 1000,
    )
    return tab


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")
    with sync_api.sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as error:
            pytest.skip(f"Chrome is not available to Playwright: {error}")
        yield launched
        launched.close()


@dataclass
class LiveSession:
    server: Server
    # Opened before the playback starts, so it sees the match go live incrementally.
    early: Tab


@pytest.fixture(scope="session")
def live_session(browser: Any, tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveSession]:
    """A server started with `--player-id`, and a tab that connected before its playback ran."""
    server = start_server(tmp_path_factory.mktemp("visualizer-with-id"), LOCAL_PLAYER)
    try:
        early = open_tab(browser, server.url)
        yield LiveSession(server, early)
        early.page.context.close()
    finally:
        stop_server(server.process)


@pytest.fixture(scope="session")
def setup_server(browser: Any, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    """A server started without `--player-id` (fresh config), so the setup card shows."""
    server = start_server(tmp_path_factory.mktemp("visualizer-no-id"))
    try:
        yield server
    finally:
        stop_server(server.process)
