"""Tests for the structured logging facility."""

import logging

from mint_computer_mcp.observability import configure_logging, log_event, logger


def test_log_event_serializes_message_and_fields(
    log_events: list[dict[str, object]],
) -> None:
    log_event(logging.INFO, "desktop tool call", tool="desktop_observe", outcome="ok")

    assert len(log_events) == 1
    event = log_events[0]

    assert event["event"] == "desktop tool call"
    assert event["level"] == "INFO"
    assert event["logger"] == "mint_computer_mcp"
    assert event["tool"] == "desktop_observe"
    assert event["outcome"] == "ok"
    assert "timestamp" in event


def test_configure_logging_attaches_a_single_handler() -> None:
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    saved_propagate = logger.propagate
    logger.handlers.clear()

    try:
        configure_logging()
        configure_logging()

        assert len(logger.handlers) == 1
        assert logger.propagate is False
    finally:
        logger.handlers[:] = saved_handlers
        logger.setLevel(saved_level)
        logger.propagate = saved_propagate
