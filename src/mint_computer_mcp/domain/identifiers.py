"""Distinct identifiers for snapshots, elements, windows, and monitors."""

from typing import NewType

SnapshotId = NewType("SnapshotId", str)
ElementRef = NewType("ElementRef", str)
WindowId = NewType("WindowId", int)
MonitorId = NewType("MonitorId", str)
