"""Exercise MCP desktop control against an owned Xvfb server."""

from typing import cast

import pytest
import xcffib
from mcp import Client
from mcp.types import CallToolResult

from mint_computer_mcp.native.x11.backend import X11Backend
from mint_computer_mcp.runtime import DesktopRuntime
from mint_computer_mcp.server import create_server

pytestmark = pytest.mark.integration


def _structured_content(result: CallToolResult) -> dict[str, object]:
    """Narrow the SDK's untyped structured-content field for assertions."""
    metadata = cast("dict[str, object] | None", result.structured_content)
    assert metadata is not None
    return metadata


@pytest.mark.anyio
async def test_mcp_observe_then_move_pointer(
    isolated_x11_display: str,
    isolated_x11_reader: xcffib.Connection,
) -> None:
    backend = X11Backend.connect(isolated_x11_display)

    with DesktopRuntime(backend) as runtime:
        server = create_server(runtime)

        async with Client(
            server,
            raise_exceptions=True,
        ) as client:
            observation = await client.call_tool(
                "desktop_observe",
                {},
            )

            snapshot_id = _structured_content(observation)["snapshot_id"]
            assert isinstance(snapshot_id, str)

            result = await client.call_tool(
                "desktop_act",
                {
                    "action": {
                        "kind": "move",
                        "snapshot_id": snapshot_id,
                        "x": 123,
                        "y": 234,
                    }
                },
            )

            assert not result.is_error

        root = isolated_x11_reader.get_setup().roots[isolated_x11_reader.pref_screen].root
        pointer = isolated_x11_reader.core.QueryPointer(root).reply()
        assert pointer.same_screen
        assert (pointer.root_x, pointer.root_y) == (123, 234)
