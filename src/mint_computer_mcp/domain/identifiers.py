"""Distinct identifiers for snapshots, elements, windows, and monitors."""

from typing import NewType

SnapshotId = NewType("SnapshotId", str)
ElementRef = NewType("ElementRef", str)
MonitorId = NewType("MonitorId", str)

# Opaque references exposed by desktop backends.
OutputRef = NewType("OutputRef", str)
WindowRef = NewType("WindowRef", str)

# x11 specific identifiers
WindowId = NewType("WindowId", int)
X11Keycode = NewType("X11Keycode", int)
RandrOutputId = NewType("RandrOutputId", int)
AtomId = NewType("AtomId", int)
