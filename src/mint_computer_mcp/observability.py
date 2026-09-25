"""Structured logging for the MCP server.

Records are written to stderr so they never corrupt the stdio MCP stream. Call
``configure_logging`` once from the composition root, then emit through
``log_event`` so tool calls, display changes, and startup land as queryable
events instead of free-form lines.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, override

_LOG_LEVEL_ENV: Final = "MINT_COMPUTER_MCP_LOG_LEVEL"

logger: Final = logging.getLogger("mint_computer_mcp")


@dataclass(frozen=True, slots=True)
class _Event:
    """The structured context attached to one record."""

    fields: dict[str, object]


class JsonFormatter(logging.Formatter):
    """Render a record and its structured fields as one JSON object."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Serialize the record's fixed fields, extras, and exception."""
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(_structured_fields(record))

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _structured_fields(record: logging.LogRecord) -> dict[str, object]:
    """Return the structured fields attached to a record, if any."""
    carrier: object = record.__dict__.get("event_fields")

    if isinstance(carrier, _Event):
        return carrier.fields

    return {}


def _resolve_level(name: str | None) -> int:
    """Resolve a level name, defaulting to INFO for missing or unknown names."""
    if name is None:
        return logging.INFO

    return logging.getLevelNamesMapping().get(name.strip().upper(), logging.INFO)


def configure_logging() -> None:
    """Attach the JSON handler to the project logger once, honouring the level env var."""
    if logger.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())

    logger.addHandler(handler)
    logger.setLevel(_resolve_level(os.environ.get(_LOG_LEVEL_ENV)))
    # The MCP SDK installs its own root handler on startup; without this every
    # event would be printed once as JSON and once as a bare message.
    logger.propagate = False


def log_event(level: int, event: str, /, **fields: object) -> None:
    """Emit one structured event carrying ``fields`` as its queryable context."""
    logger.log(level, event, extra={"event_fields": _Event(fields)})
