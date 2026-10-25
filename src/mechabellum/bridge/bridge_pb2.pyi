from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CompetitionSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    COMPETITION_SOURCE_UNSPECIFIED: _ClassVar[CompetitionSource]
    COMPETITION_SOURCE_HISTORY: _ClassVar[CompetitionSource]
    COMPETITION_SOURCE_RECENT: _ClassVar[CompetitionSource]
COMPETITION_SOURCE_UNSPECIFIED: CompetitionSource
COMPETITION_SOURCE_HISTORY: CompetitionSource
COMPETITION_SOURCE_RECENT: CompetitionSource

class Envelope(_message.Message):
    __slots__ = ("id", "error", "status_request", "status_reply", "list_competitions_request", "list_competitions_reply", "competition_page_request", "competition_page_reply", "download_replay_request", "download_replay_reply")
    ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    STATUS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    STATUS_REPLY_FIELD_NUMBER: _ClassVar[int]
    LIST_COMPETITIONS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    LIST_COMPETITIONS_REPLY_FIELD_NUMBER: _ClassVar[int]
    COMPETITION_PAGE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    COMPETITION_PAGE_REPLY_FIELD_NUMBER: _ClassVar[int]
    DOWNLOAD_REPLAY_REQUEST_FIELD_NUMBER: _ClassVar[int]
    DOWNLOAD_REPLAY_REPLY_FIELD_NUMBER: _ClassVar[int]
    id: int
    error: Error
    status_request: StatusRequest
    status_reply: StatusReply
    list_competitions_request: ListCompetitionsRequest
    list_competitions_reply: ListCompetitionsReply
    competition_page_request: CompetitionPageRequest
    competition_page_reply: CompetitionPageReply
    download_replay_request: DownloadReplayRequest
    download_replay_reply: DownloadReplayReply
    def __init__(self, id: _Optional[int] = ..., error: _Optional[_Union[Error, _Mapping]] = ..., status_request: _Optional[_Union[StatusRequest, _Mapping]] = ..., status_reply: _Optional[_Union[StatusReply, _Mapping]] = ..., list_competitions_request: _Optional[_Union[ListCompetitionsRequest, _Mapping]] = ..., list_competitions_reply: _Optional[_Union[ListCompetitionsReply, _Mapping]] = ..., competition_page_request: _Optional[_Union[CompetitionPageRequest, _Mapping]] = ..., competition_page_reply: _Optional[_Union[CompetitionPageReply, _Mapping]] = ..., download_replay_request: _Optional[_Union[DownloadReplayRequest, _Mapping]] = ..., download_replay_reply: _Optional[_Union[DownloadReplayReply, _Mapping]] = ...) -> None: ...

class Error(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class StatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StatusReply(_message.Message):
    __slots__ = ("protocol_version", "mod_version", "game_version", "online", "replay_directory", "server_request_interval_ms")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    MOD_VERSION_FIELD_NUMBER: _ClassVar[int]
    GAME_VERSION_FIELD_NUMBER: _ClassVar[int]
    ONLINE_FIELD_NUMBER: _ClassVar[int]
    REPLAY_DIRECTORY_FIELD_NUMBER: _ClassVar[int]
    SERVER_REQUEST_INTERVAL_MS_FIELD_NUMBER: _ClassVar[int]
    protocol_version: int
    mod_version: str
    game_version: str
    online: bool
    replay_directory: str
    server_request_interval_ms: int
    def __init__(self, protocol_version: _Optional[int] = ..., mod_version: _Optional[str] = ..., game_version: _Optional[str] = ..., online: _Optional[bool] = ..., replay_directory: _Optional[str] = ..., server_request_interval_ms: _Optional[int] = ...) -> None: ...

class ListCompetitionsRequest(_message.Message):
    __slots__ = ("page",)
    PAGE_FIELD_NUMBER: _ClassVar[int]
    page: int
    def __init__(self, page: _Optional[int] = ...) -> None: ...

class ListCompetitionsReply(_message.Message):
    __slots__ = ("page", "page_count", "competitions")
    PAGE_FIELD_NUMBER: _ClassVar[int]
    PAGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    COMPETITIONS_FIELD_NUMBER: _ClassVar[int]
    page: int
    page_count: int
    competitions: _containers.RepeatedCompositeFieldContainer[Competition]
    def __init__(self, page: _Optional[int] = ..., page_count: _Optional[int] = ..., competitions: _Optional[_Iterable[_Union[Competition, _Mapping]]] = ...) -> None: ...

class Competition(_message.Message):
    __slots__ = ("id", "start_time", "sub_ids", "source")
    ID_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    SUB_IDS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    id: int
    start_time: int
    sub_ids: _containers.RepeatedScalarFieldContainer[int]
    source: CompetitionSource
    def __init__(self, id: _Optional[int] = ..., start_time: _Optional[int] = ..., sub_ids: _Optional[_Iterable[int]] = ..., source: _Optional[_Union[CompetitionSource, str]] = ...) -> None: ...

class CompetitionPageRequest(_message.Message):
    __slots__ = ("competition_id", "sub_id", "page")
    COMPETITION_ID_FIELD_NUMBER: _ClassVar[int]
    SUB_ID_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    competition_id: int
    sub_id: int
    page: int
    def __init__(self, competition_id: _Optional[int] = ..., sub_id: _Optional[int] = ..., page: _Optional[int] = ...) -> None: ...

class CompetitionPageReply(_message.Message):
    __slots__ = ("competition_id", "sub_id", "page", "page_count", "state", "replay_paths", "results")
    COMPETITION_ID_FIELD_NUMBER: _ClassVar[int]
    SUB_ID_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    PAGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    REPLAY_PATHS_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    competition_id: int
    sub_id: int
    page: int
    page_count: int
    state: int
    replay_paths: _containers.RepeatedScalarFieldContainer[str]
    results: _containers.RepeatedCompositeFieldContainer[ReplayResult]
    def __init__(self, competition_id: _Optional[int] = ..., sub_id: _Optional[int] = ..., page: _Optional[int] = ..., page_count: _Optional[int] = ..., state: _Optional[int] = ..., replay_paths: _Optional[_Iterable[str]] = ..., results: _Optional[_Iterable[_Union[ReplayResult, _Mapping]]] = ...) -> None: ...

class ReplayResult(_message.Message):
    __slots__ = ("replay_path", "winner_user_id", "loser_user_id")
    REPLAY_PATH_FIELD_NUMBER: _ClassVar[int]
    WINNER_USER_ID_FIELD_NUMBER: _ClassVar[int]
    LOSER_USER_ID_FIELD_NUMBER: _ClassVar[int]
    replay_path: str
    winner_user_id: int
    loser_user_id: int
    def __init__(self, replay_path: _Optional[str] = ..., winner_user_id: _Optional[int] = ..., loser_user_id: _Optional[int] = ...) -> None: ...

class DownloadReplayRequest(_message.Message):
    __slots__ = ("replay_path",)
    REPLAY_PATH_FIELD_NUMBER: _ClassVar[int]
    replay_path: str
    def __init__(self, replay_path: _Optional[str] = ...) -> None: ...

class DownloadReplayReply(_message.Message):
    __slots__ = ("replay_path", "file_path", "downloaded")
    REPLAY_PATH_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    DOWNLOADED_FIELD_NUMBER: _ClassVar[int]
    replay_path: str
    file_path: str
    downloaded: bool
    def __init__(self, replay_path: _Optional[str] = ..., file_path: _Optional[str] = ..., downloaded: _Optional[bool] = ...) -> None: ...
