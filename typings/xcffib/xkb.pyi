# Read-only XKB requests used to independently verify server state in integration tests.

from . import Cookie, ExtensionKey

class UseExtensionReply:
    supported: bool

class UseExtensionCookie(Cookie[UseExtensionReply]): ...

class GetStateReply:
    lockedMods: int  # noqa: N815 - generated protocol field.

class GetStateCookie(Cookie[GetStateReply]): ...

class xkbExtension:
    def UseExtension(
        self, wantedMajor: int, wantedMinor: int, is_checked: bool = ...
    ) -> UseExtensionCookie: ...
    def GetState(self, deviceSpec: int, is_checked: bool = ...) -> GetStateCookie: ...

key: ExtensionKey[xkbExtension]
