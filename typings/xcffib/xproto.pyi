# Core protocol requests and reply fields consumed by the adapter.

from typing import ClassVar

from . import Cookie, Error, List

class Atom:
    WINDOW: ClassVar[int]
    CARDINAL: ClassVar[int]

class WindowError(Error): ...
class DrawableError(Error): ...

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

class GetGeometryReply:
    root: int
    x: int
    y: int
    width: int
    height: int
    border_width: int

class TranslateCoordinatesReply:
    same_screen: bool
    child: int
    dst_x: int
    dst_y: int

class ListExtensionsCookie(Cookie[ListExtensionsReply]): ...
class InternAtomCookie(Cookie[InternAtomReply]): ...
class GetPropertyCookie(Cookie[GetPropertyReply]): ...
class GetGeometryCookie(Cookie[GetGeometryReply]): ...
class TranslateCoordinatesCookie(Cookie[TranslateCoordinatesReply]): ...

class xprotoExtension:
    def ListExtensions(self, is_checked: bool = ...) -> ListExtensionsCookie: ...
    def InternAtom(
        self,
        only_if_exists: bool,
        name_len: int,
        name: bytes | str,
        is_checked: bool = ...,
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
    def GetGeometry(
        self,
        drawable: int,
        is_checked: bool = ...,
    ) -> GetGeometryCookie: ...
    def TranslateCoordinates(
        self,
        src_window: int,
        dst_window: int,
        src_x: int,
        src_y: int,
        is_checked: bool = ...,
    ) -> TranslateCoordinatesCookie: ...
