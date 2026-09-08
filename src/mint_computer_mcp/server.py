"""MCP protocol."""

import base64
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ImageContent, TextContent

from mint_computer_mcp.api.action import ActionResult, DesktopAction, to_domain_action
from mint_computer_mcp.api.observation import (
    DesktopObservationTarget,
    DesktopObserveTarget,
    ObserveMetadata,
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
from mint_computer_mcp.runtime import (
    DesktopRuntime,
    StaleSnapshotError,
)

_DEFAULT_OBSERVE_TARGET = DesktopObservationTarget(kind="desktop")


def create_server[SnapshotStateT](  # noqa: C901
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
        try:
            observation = runtime.observe(
                to_domain_target(target),
            )
        except TargetUnavailableError as exc:
            msg = "TARGET_UNAVAILABLE: requested observation target is not currently capturable"
            raise ToolError(msg) from exc
        except CapabilityUnavailableError as exc:
            msg_0 = "CAPABILITY_UNAVAILABLE: the desktop backend cannot provide this observation"
            raise ToolError(msg_0) from exc

        metadata = from_domain_observation(observation)

        encoded_image = base64.b64encode(observation.image.data).decode("ascii")

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
        try:
            runtime.act(
                to_domain_action(action),
            )
        except StaleSnapshotError as exc:
            msg = "STALE_SNAPSHOT: observe again and use the new snapshot_id"
            raise ToolError(msg) from exc
        except UnsupportedKeyError as exc:
            msg_0 = "UNSUPPORTED_KEY: the current keyboard map cannot resolve the requested key"
            raise ToolError(msg_0) from exc
        except UnsupportedTextInputError as exc:
            msg_1 = (
                "UNSUPPORTED_TEXT_INPUT: the current keyboard map "
                "cannot safely produce the requested text"
            )
            raise ToolError(msg_1) from exc
        except KeyboardStateConflictError as exc:
            msg_2 = "KEYBOARD_STATE_CONFLICT: existing keyboard state makes this input unsafe"
            raise ToolError(msg_2) from exc
        except InputStateUncertainError as exc:
            msg_3 = (
                "INPUT_STATE_UNCERTAIN: synthetic input cleanup could "
                "not be guaranteed; do not continue blindly"
            )
            raise ToolError(msg_3) from exc
        except CapabilityUnavailableError as exc:
            msg_4 = "CAPABILITY_UNAVAILABLE: the desktop backend cannot perform this action"
            raise ToolError(msg_4) from exc

        return ActionResult()

    return server
