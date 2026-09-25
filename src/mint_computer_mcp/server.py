"""MCP protocol."""

import base64
import logging
from collections.abc import Mapping
from time import monotonic
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ImageContent, TextContent

from mint_computer_mcp.api.action import (
    ActionResult,
    ClickAction,
    DesktopAction,
    MoveAction,
    to_domain_action,
)
from mint_computer_mcp.api.observation import (
    DesktopObservationTarget,
    DesktopObserveTarget,
    ObserveMetadata,
    OutputObservationTarget,
    from_domain_observation,
    to_domain_target,
)
from mint_computer_mcp.backend import (
    CapabilityUnavailableError,
    InputStateUncertainError,
    KeyboardStateConflictError,
    TargetUnavailableError,
    UnsupportedKeyError,
    UnsupportedTextInputError,
)
from mint_computer_mcp.observability import log_event
from mint_computer_mcp.runtime import (
    DesktopRuntime,
    StaleSnapshotError,
)

_DEFAULT_OBSERVE_TARGET = DesktopObservationTarget(kind="desktop")


def _observe_context(target: DesktopObserveTarget) -> dict[str, object]:
    """Identify the requested observation target without logging its payload."""
    if isinstance(target, OutputObservationTarget):
        return {"target_kind": target.kind, "output_ref": str(target.output)}

    return {"target_kind": target.kind}


def _action_context(action: DesktopAction) -> dict[str, object]:
    """Identify the action kind; typed text and key names are never logged."""
    if isinstance(action, (ClickAction, MoveAction)):
        return {"action_kind": action.kind, "snapshot_id": str(action.snapshot_id)}

    return {"action_kind": action.kind}


def _log_tool_call(
    tool: str,
    started_at: float,
    context: Mapping[str, object],
    error: Exception | None = None,
) -> None:
    """Emit one event per tool call, carrying the failure reason on error."""
    fields: dict[str, object] = {
        "tool": tool,
        "outcome": "error" if error is not None else "ok",
        "duration_ms": round((monotonic() - started_at) * 1000, 3),
        **context,
    }

    if error is not None:
        fields["error_type"] = type(error).__name__
        fields["error"] = str(error)

    log_event(logging.ERROR if error is not None else logging.INFO, "desktop tool call", **fields)


def create_server[SnapshotStateT](  # noqa: C901, PLR0915
    runtime: DesktopRuntime[SnapshotStateT],
) -> MCPServer[None]:
    """Create mcp server."""
    # TODO: proper instructions.  # noqa: FIX002, TD002, TD003
    server = MCPServer[None](
        name="mint-computer-mcp", instructions=("use for computer use realted tasks.")
    )

    @server.tool()
    async def desktop_observe(  # pyright: ignore[reportUnusedFunction]
        target: DesktopObserveTarget = _DEFAULT_OBSERVE_TARGET,
    ) -> Annotated[CallToolResult, ObserveMetadata]:
        """Capture a JPEG observation and return snapshot-relative metadata."""
        started_at = monotonic()
        context = _observe_context(target)

        try:
            observation = runtime.observe(
                to_domain_target(target),
            )
        except TargetUnavailableError as exc:
            _log_tool_call("desktop_observe", started_at, context, exc)
            msg = "TARGET_UNAVAILABLE: requested observation target is not currently capturable"
            raise ToolError(msg) from exc
        except CapabilityUnavailableError as exc:
            _log_tool_call("desktop_observe", started_at, context, exc)
            msg_0 = "CAPABILITY_UNAVAILABLE: the desktop backend cannot provide this observation"
            raise ToolError(msg_0) from exc

        metadata = from_domain_observation(observation)

        encoded_image = base64.b64encode(observation.image.data).decode("ascii")

        _log_tool_call(
            "desktop_observe",
            started_at,
            {
                **context,
                "snapshot_id": str(metadata.snapshot_id),
                "output_count": len(metadata.outputs),
            },
        )

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        f"snapshot_id={metadata.snapshot_id} "
                        f"size={metadata.encoded_size.width}x"
                        f"{metadata.encoded_size.height}"
                    ),
                ),
                ImageContent(
                    type="image",
                    data=encoded_image,
                    mime_type="image/jpeg",
                ),
            ],
            structured_content=metadata.model_dump(),
        )

    @server.tool()
    async def desktop_act(  # pyright: ignore[reportUnusedFunction]
        action: DesktopAction,
    ) -> ActionResult:
        """Execute one validated desktop input action."""
        started_at = monotonic()
        context = _action_context(action)

        try:
            runtime.act(
                to_domain_action(action),
            )
        except StaleSnapshotError as exc:
            _log_tool_call("desktop_act", started_at, context, exc)
            msg = "STALE_SNAPSHOT: observe again and use the new snapshot_id"
            raise ToolError(msg) from exc
        except UnsupportedKeyError as exc:
            _log_tool_call("desktop_act", started_at, context, exc)
            msg_0 = "UNSUPPORTED_KEY: the current keyboard map cannot resolve the requested key"
            raise ToolError(msg_0) from exc
        except UnsupportedTextInputError as exc:
            _log_tool_call("desktop_act", started_at, context, exc)
            msg_1 = (
                "UNSUPPORTED_TEXT_INPUT: the current keyboard map "
                "cannot safely produce the requested text"
            )
            raise ToolError(msg_1) from exc
        except KeyboardStateConflictError as exc:
            _log_tool_call("desktop_act", started_at, context, exc)
            msg_2 = "KEYBOARD_STATE_CONFLICT: existing keyboard state makes this input unsafe"
            raise ToolError(msg_2) from exc
        except InputStateUncertainError as exc:
            _log_tool_call("desktop_act", started_at, context, exc)
            msg_3 = (
                "INPUT_STATE_UNCERTAIN: synthetic input cleanup could "
                "not be guaranteed; do not continue blindly"
            )
            raise ToolError(msg_3) from exc
        except CapabilityUnavailableError as exc:
            _log_tool_call("desktop_act", started_at, context, exc)
            msg_4 = "CAPABILITY_UNAVAILABLE: the desktop backend cannot perform this action"
            raise ToolError(msg_4) from exc

        _log_tool_call("desktop_act", started_at, context)

        return ActionResult()

    return server
