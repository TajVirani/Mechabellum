from __future__ import annotations

import itertools
from typing import Any

from . import bridge_pb2 as pb

DEFAULT_PORT = 17615
PROTOCOL_VERSION = 1


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class BridgeClient:
    """Synchronous client for the MechaBridge mod's WebSocket server (contracts/bridge/v1/bridge.proto)."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._ids = itertools.count(1)

    @classmethod
    def connect(cls, port: int = DEFAULT_PORT, timeout: float = 5.0) -> BridgeClient:
        from websockets.sync.client import connect

        try:
            connection = connect(f"ws://127.0.0.1:{port}/", open_timeout=timeout, max_size=None)
        except OSError as error:
            raise BridgeError(
                "not_connected", f"MechaBridge is not reachable on port {port}; is the game running with the mod?"
            ) from error
        return cls(connection)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> BridgeClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self) -> pb.StatusReply:
        return self._call("status_request", pb.StatusRequest(), "status_reply", timeout=10)

    def list_competitions(self, page: int) -> pb.ListCompetitionsReply:
        return self._call("list_competitions_request", pb.ListCompetitionsRequest(page=page), "list_competitions_reply")

    def competition_page(self, competition_id: int, sub_id: int, page: int) -> pb.CompetitionPageReply:
        request = pb.CompetitionPageRequest(competition_id=competition_id, sub_id=sub_id, page=page)
        return self._call("competition_page_request", request, "competition_page_reply")

    def download_replay(self, replay_path: str) -> pb.DownloadReplayReply:
        request = pb.DownloadReplayRequest(replay_path=replay_path)
        return self._call("download_replay_request", request, "download_replay_reply", timeout=180)

    def _call(self, request_field: str, request: Any, reply_field: str, timeout: float = 90) -> Any:
        envelope = pb.Envelope(id=next(self._ids))
        getattr(envelope, request_field).CopyFrom(request)
        self._connection.send(envelope.SerializeToString())
        while True:
            try:
                frame = self._connection.recv(timeout=timeout)
            except TimeoutError as error:
                raise BridgeError("timeout", f"no reply to {request_field} within {timeout:g} s") from error
            if isinstance(frame, str):
                continue
            reply = pb.Envelope.FromString(frame)
            if reply.id != envelope.id:
                # Events (id 0) and stale replies are not ours.
                continue
            body = reply.WhichOneof("body")
            if body == "error":
                raise BridgeError(reply.error.code, reply.error.message)
            if body != reply_field:
                raise BridgeError("invalid_reply", f"expected {reply_field}, got {body}")
            return getattr(reply, reply_field)
