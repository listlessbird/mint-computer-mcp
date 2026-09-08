import base64
from collections.abc import AsyncIterator
from typing import cast

import pytest
from mcp import Client
from mcp.types import CallToolResult, ImageContent
from syrupy.assertion import SnapshotAssertion

from mint_computer_mcp.runtime import DesktopRuntime
from mint_computer_mcp.server import create_server
from tests.support import FakeBackend, FakeSnapshotState


def _structured_content(result: CallToolResult) -> dict[str, object]:
    """Narrow the SDK's untyped structured-content field for assertions."""
    metadata = cast("dict[str, object] | None", result.structured_content)
    assert metadata is not None
    return metadata


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[tuple[Client, FakeBackend]]:
    backend = FakeBackend()

    with DesktopRuntime[FakeSnapshotState](backend) as runtime:
        server = create_server(runtime)

        async with Client(
            server,
            raise_exceptions=True,
        ) as connected_client:
            yield connected_client, backend


@pytest.mark.anyio
async def test_server_exposes_only_initial_desktop_tools(
    client: tuple[Client, FakeBackend],
) -> None:
    connected_client, _ = client
    tools = await connected_client.list_tools()

    assert {tool.name for tool in tools.tools} == {
        "desktop_observe",
        "desktop_act",
    }


@pytest.mark.anyio
async def test_server_tool_schemas(snapshot: SnapshotAssertion) -> None:
    backend = FakeBackend()

    with DesktopRuntime[FakeSnapshotState](backend) as runtime:
        server = create_server(runtime)

        async with Client(
            server,
            raise_exceptions=True,
        ) as client:
            tools = await client.list_tools()

    schemas = {
        tool.name: {
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
        }
        for tool in tools.tools
    }

    assert schemas == snapshot


@pytest.mark.anyio
async def test_desktop_observe_returns_jpeg_and_metadata(
    client: tuple[Client, FakeBackend],
) -> None:
    connected_client, _ = client
    result = await connected_client.call_tool(
        "desktop_observe",
        {},
    )

    assert not result.is_error
    metadata = _structured_content(result)

    images = [item for item in result.content if isinstance(item, ImageContent)]

    assert len(images) == 1

    image = images[0]

    assert image.mime_type == "image/jpeg"

    jpeg = base64.b64decode(
        image.data,
        validate=True,
    )

    assert jpeg.startswith(b"\xff\xd8")

    snapshot_id = metadata["snapshot_id"]
    assert isinstance(snapshot_id, str)
    assert snapshot_id.startswith("snap_")
    assert metadata["encoded_size"] == {
        "width": 2,
        "height": 2,
    }
    assert "image" not in metadata
    assert "data" not in metadata


@pytest.mark.anyio
async def test_desktop_act_dispatches_spatial_action(
    client: tuple[Client, FakeBackend],
) -> None:
    connected_client, backend = client
    observation = await connected_client.call_tool(
        "desktop_observe",
        {},
    )

    metadata = _structured_content(observation)
    snapshot_id = metadata["snapshot_id"]
    assert isinstance(snapshot_id, str)

    result = await connected_client.call_tool(
        "desktop_act",
        {
            "action": {
                "kind": "move",
                "snapshot_id": snapshot_id,
                "x": 1,
                "y": 0,
            },
        },
    )

    assert not result.is_error
    assert backend.moves
