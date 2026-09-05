# Core protocol requests and reply fields consumed by the adapter.

from typing import ClassVar

from . import Cookie, Error, List

class Atom:
    WINDOW: ClassVar[int]

class WindowError(Error): ...

class SCREEN:
    root: int
    width_in_pixels: int
    height_in_pixels: int

class Setup:
    vendor: List[bytes]
    protocol_major_version: int
    protocol_minor_version: int
    release_number: int
    roots: List[SCREEN]

class STR:
    name: List[bytes]

class ListExtensionsReply:
    names: List[STR]

class InternAtomReply:
    atom: int

class GetPropertyReply:
    type: int
    format: int
    value_len: int
    bytes_after: int
    value: List[bytes]

class ListExtensionsCookie(Cookie[ListExtensionsReply]): ...
class InternAtomCookie(Cookie[InternAtomReply]): ...
class GetPropertyCookie(Cookie[GetPropertyReply]): ...

class xprotoExtension:
    def ListExtensions(self, is_checked: bool = ...) -> ListExtensionsCookie: ...
    def InternAtom(
        self, only_if_exists: bool, name_len: int, name: bytes | str, is_checked: bool = ...
    ) -> InternAtomCookie: ...
    def GetProperty(
        self,
        delete: bool,
        window: int,
        property: int,
        type: int,
        long_offset: int,
        long_length: int,
        is_checked: bool = ...,
    ) -> GetPropertyCookie: ...
