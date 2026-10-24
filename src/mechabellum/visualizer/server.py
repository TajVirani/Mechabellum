"""The Visualizer's HTTP server: static files, the `/events` SSE stream and `/api/local-player`.

Binds 127.0.0.1 only. Nothing here talks to the game server.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .cache import CONFIG_NAME, DATABASE_NAME, SummaryCache, VisualizerConfig, default_data_dir
from .hub import CLOSED, Hub
from .live import LiveProcessor, load_predictor, model_looks_available, run_bridge_probe, run_memory, run_playback
from .roles import catalog
from .watcher import ReplayWatcher

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_DIR = Path(__file__).resolve().parent / "static"
KEEPALIVE_SECONDS = 15.0
# How long close() waits for each worker thread before closing the cache under it.
SHUTDOWN_JOIN_SECONDS = 5.0
MAX_BODY_BYTES = 4096
# Served at / until the frontend's static/index.html exists.
PLACEHOLDER_PAGE = (
    b'<!doctype html><meta charset="utf-8"><title>Mechabellum Visualizer</title>'
    b"<p>The Visualizer frontend is not installed (static/index.html is missing). The event stream is at "
    b'<a href="/events">/events</a>.</p>'
)
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


@dataclass
class VisualizerOptions:
    port: int = DEFAULT_PORT
    open_browser: bool = True
    replay_dir: Path | None = None
    data_dir: Path | None = None
    player_id: str | None = None
    playback: Path | None = None
    playback_speed: float = 1.0
    model: Path = field(default_factory=lambda: Path("artifacts/win_model.joblib"))
    live: bool = True


class Visualizer:
    """Everything one `mecha visualize` runs: hub, cache, replay watcher, live thread and HTTP server."""

    def __init__(self, options: VisualizerOptions, *, static_dir: Path = STATIC_DIR) -> None:
        self.options = options
        data_dir = options.data_dir or default_data_dir()
        self.config = VisualizerConfig(data_dir / CONFIG_NAME)
        if options.player_id:
            self.config.set_local_player_id(options.player_id)
        self.cache = SummaryCache(data_dir / DATABASE_NAME)
        # The model stack takes seconds to import, so the live thread loads it; until then this is a guess.
        self.model_expected = options.live and model_looks_available(options.model)
        live_source = "none" if not options.live else "playback" if options.playback else "memory"
        replay_dir = options.replay_dir
        self.hub = Hub(
            server_version=_server_version(),
            model_available=self.model_expected,
            replay_dir=None if replay_dir is None else str(replay_dir),
            live_source=live_source,
            local_player_id=self.config.local_player_id,
        )
        self.processor = LiveProcessor(self.hub, self.cache)
        self.watcher = (
            None
            if replay_dir is None
            else ReplayWatcher(replay_dir, self.cache, self.hub.upsert_summary, on_summaries=self.hub.set_summaries)
        )
        self.stop_event = threading.Event()
        self.httpd = _Server((HOST, options.port), _Handler)
        self.httpd.visualizer = self
        self.static_dir = static_dir.resolve()
        self._threads: list[threading.Thread] = []
        self._serving = False

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.httpd.server_address[1]}/"

    def start(self) -> None:
        """Load the summaries and ratings, then start the watcher, the live source and the HTTP server threads."""
        if self.watcher is not None:
            self.hub.set_summaries(self.watcher.scan_existing())
            self.watcher.start()
        self.hub.set_ratings(self.cache.ratings())
        options = self.options
        if options.live:
            self._spawn("live", self._run_live)
            if options.playback is None:
                self._spawn("bridge-probe", run_bridge_probe, self.hub, self.stop_event)
        self._spawn("http", self.httpd.serve_forever)
        self._serving = True

    def wait_until_live_done(self, timeout: float | None = None) -> bool:
        """Wait for the live thread to finish (a playback's end); True when it has."""
        thread = next((thread for thread in self._threads if thread.name == "live"), None)
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run_live(self) -> None:
        options = self.options
        if self.model_expected:
            predictor = load_predictor(options.model)
            if predictor is None:
                print(f"Win probability model unavailable: {options.model}", file=sys.stderr, flush=True)
                self.hub.set_model_available(False)
            self.processor.set_predictor(predictor)
        if options.playback is not None:
            run_playback(self.processor, self.hub, options.playback, self.stop_event, speed=options.playback_speed)
        else:
            run_memory(self.processor, self.hub, self.stop_event)

    def set_local_player(self, player_id: str | None) -> None:
        self.config.set_local_player_id(player_id)
        self.hub.set_local_player(player_id)
        self.processor.refresh_local_player()

    def close(self) -> None:
        """Stop everything; the watcher and live threads are joined (bounded) before the cache they write closes."""
        self.stop_event.set()
        if self.watcher is not None:
            self.watcher.stop(timeout=SHUTDOWN_JOIN_SECONDS)
        for thread in self._threads:
            if thread.name != "http" and thread is not threading.current_thread():
                thread.join(SHUTDOWN_JOIN_SECONDS)
        self.hub.close()
        if self._serving:
            self.httpd.shutdown()
        self.httpd.server_close()
        self.cache.close()

    def _spawn(self, name: str, target: Any, *args: Any, **kwargs: Any) -> None:
        thread = threading.Thread(target=target, args=args, kwargs=kwargs, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)


def run(options: VisualizerOptions) -> None:
    """Serve until interrupted. Prints `Visualizer: <url>` once the port is bound."""
    visualizer = Visualizer(options)
    try:
        visualizer.start()
        print(f"Visualizer: {visualizer.url}", flush=True)
        if options.live and not visualizer.model_expected:
            print(f"Win probability model unavailable: {options.model}", file=sys.stderr, flush=True)
        if options.open_browser:
            webbrowser.open(visualizer.url)
        visualizer.stop_event.wait()
    finally:
        visualizer.close()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    visualizer: Visualizer


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        if not self._host_allowed():
            return
        path = urlsplit(self.path).path
        if path == "/events":
            self._events()
        elif path == "/catalog.json":
            self._json(HTTPStatus.OK, catalog())
        elif path == "/api/local-player":
            hub = self.server.visualizer.hub
            self._json(
                HTTPStatus.OK, {"localPlayerId": hub.local_player_id, "suggestedPlayerId": hub.suggested_player_id}
            )
        else:
            self._static(path)

    def do_HEAD(self) -> None:
        if self._host_allowed():
            self._static(urlsplit(self.path).path, head=True)

    def do_POST(self) -> None:
        if not self._host_allowed():
            return
        if urlsplit(self.path).path != "/api/local-player":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                raise ValueError("body too large")
            body = json.loads(self.rfile.read(length) or b"{}")
            player_id = body.get("playerId") if isinstance(body, dict) else None
            if player_id is not None:
                player_id = str(player_id).strip() or None
            if player_id is not None and (len(player_id) > 64 or not player_id.isprintable()):
                raise ValueError("invalid playerId")
        except ValueError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self.server.visualizer.set_local_player(player_id)
        self._json(HTTPStatus.OK, {"localPlayerId": player_id})

    # ---- responses -------------------------------------------------------------------------------------------

    def _host_allowed(self) -> bool:
        """Refuse requests whose Host or Origin isn't this server, so other sites can't reach it via DNS tricks."""
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        host_ok = self.headers.get("Host") in allowed
        origin_ok = origin is None or urlsplit(origin).netloc in allowed
        if host_ok and origin_ok:
            return True
        self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden host"})
        return False

    def _events(self) -> None:
        hub = self.server.visualizer.hub
        self.close_connection = True
        client = None
        try:
            # Subscribed inside the try, so a client gone before the headers are written is always unsubscribed.
            client = hub.subscribe()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b"retry: 2000\n\n")
            while True:
                try:
                    message = client.get(timeout=KEEPALIVE_SECONDS)
                except queue.Empty:
                    message = b": keepalive\n\n"
                if message is CLOSED:
                    break
                self.wfile.write(message)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        finally:
            if client is not None:
                hub.unsubscribe(client)

    def _static(self, path: str, head: bool = False) -> None:
        root = self.server.visualizer.static_dir
        relative = unquote(path).lstrip("/") or "index.html"
        try:
            target = (root / relative).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            target = None
        if target is not None and target.is_dir():
            target = target / "index.html"
        if target is None or not target.is_file():
            if relative != "index.html":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            body, content_type = PLACEHOLDER_PAGE, CONTENT_TYPES[".html"]
        else:
            body, content_type = (
                target.read_bytes(),
                CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream"),
            )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _json(self, status: HTTPStatus, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _server_version() -> str:
    try:
        from importlib.metadata import version

        return version("mechabellum-analytics")
    except Exception:
        return "0.0.0"
