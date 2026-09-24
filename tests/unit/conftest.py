"""Shared fixtures for unit tests."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, cast, override

import pytest

from mint_computer_mcp.observability import JsonFormatter, logger

if TYPE_CHECKING:
    from collections.abc import Iterator


class _EventCaptureHandler(logging.Handler):
    """Parse each emitted record's JSON into a shared list."""

    def __init__(self, events: list[dict[str, object]]) -> None:
        super().__init__()
        self._events: list[dict[str, object]] = events

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self._events.append(cast("dict[str, object]", json.loads(self.format(record))))


@pytest.fixture
def log_events() -> Iterator[list[dict[str, object]]]:
    """Capture the structured events emitted through the project logger."""
    events: list[dict[str, object]] = []
    handler = _EventCaptureHandler(events)
    handler.setFormatter(JsonFormatter())

    previous_level = logger.level
    previous_propagate = logger.propagate

    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        yield events
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
