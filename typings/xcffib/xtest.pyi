from . import ExtensionKey, VoidCookie

MAJOR_VERSION: int
MINOR_VERSION: int

key: ExtensionKey[xtestExtension]

class GetVersionReply:
    major_version: int
    minor_version: int

class GetVersionCookie:
    def reply(self) -> GetVersionReply: ...

class xtestExtension:
    def GetVersion(
        self,
        major_version: int,
        minor_version: int,
        is_checked: bool = ...,
    ) -> GetVersionCookie: ...
    def FakeInput(
        self,
        type: int,
        detail: int,
        time: int,
        root: int,
        rootX: int,
        rootY: int,
        deviceid: int,
        is_checked: bool = ...,
    ) -> VoidCookie: ...
