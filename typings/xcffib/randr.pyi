# RandR requests and reply fields consumed by the adapter.

from typing import ClassVar

from . import Cookie, ExtensionKey, List

MAJOR_VERSION: int
MINOR_VERSION: int
key: ExtensionKey[randrExtension]

class Connection:
    Connected: ClassVar[int]
    Disconnected: ClassVar[int]

class QueryVersionReply:
    major_version: int
    minor_version: int

class GetScreenResourcesReply:
    outputs: List[int]

class GetOutputPrimaryReply:
    output: int

class GetOutputInfoReply:
    connection: int
    crtc: int
    name: List[int]

class GetCrtcInfoReply:
    x: int
    y: int
    width: int
    height: int

class QueryVersionCookie(Cookie[QueryVersionReply]): ...
class GetScreenResourcesCookie(Cookie[GetScreenResourcesReply]): ...
class GetOutputPrimaryCookie(Cookie[GetOutputPrimaryReply]): ...
class GetOutputInfoCookie(Cookie[GetOutputInfoReply]): ...
class GetCrtcInfoCookie(Cookie[GetCrtcInfoReply]): ...

class randrExtension:
    def QueryVersion(
        self, major_version: int, minor_version: int, is_checked: bool = ...
    ) -> QueryVersionCookie: ...
    def GetScreenResources(
        self, window: int, is_checked: bool = ...
    ) -> GetScreenResourcesCookie: ...
    def GetScreenResourcesCurrent(
        self, window: int, is_checked: bool = ...
    ) -> GetScreenResourcesCookie: ...
    def GetOutputPrimary(self, window: int, is_checked: bool = ...) -> GetOutputPrimaryCookie: ...
    def GetOutputInfo(
        self, output: int, config_timestamp: int, is_checked: bool = ...
    ) -> GetOutputInfoCookie: ...
    def GetCrtcInfo(
        self, crtc: int, config_timestamp: int, is_checked: bool = ...
    ) -> GetCrtcInfoCookie: ...
