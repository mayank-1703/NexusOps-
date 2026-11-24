"""Tests for JSON-RPC 2.0 and MCP protocol compliance."""

import pytest
from nexusops.protocol.models import JSONRPCErrorCode
from nexusops.protocol.server import MCPServer
from nexusops.security.rbac import Role, UserContext


@pytest.fixture
def mcp():
    return MCPServer(name="TestMCP", version="1.0.0")


@pytest.fixture
def admin_user():
    return UserContext(identity="test-admin", role=Role.ADMIN)


@pytest.fixture
def readonly_user():
    return UserContext(identity="test-viewer", role=Role.READONLY)


@pytest.mark.asyncio
async def test_initialize_handshake(mcp):
    """Test protocol version negotiation and server capabilities advertisement."""
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"roots": {}},
            "clientInfo": {"name": "TestClient", "version": "1.0"},
        },
    }
    resp = await mcp.handle_message(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "result" in resp
    res = resp["result"]
    assert res["protocolVersion"] == "2024-11-05"
    assert "tools" in res["capabilities"]
    assert res["serverInfo"]["name"] == "TestMCP"


@pytest.mark.asyncio
async def test_notifications_initialized(mcp):
    """Test that notifications do not yield a response body."""
    req = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    resp = await mcp.handle_message(req)
    assert resp is None
    assert mcp.initialized is True


@pytest.mark.asyncio
async def test_ping(mcp):
    """Test ping method."""
    req = {"jsonrpc": "2.0", "id": "ping-1", "method": "ping"}
    resp = await mcp.handle_message(req)
    assert resp["id"] == "ping-1"
    assert resp["result"] == {}


@pytest.mark.asyncio
async def test_tools_list_discovery(mcp, readonly_user):
    """Test dynamic tool discovery via tools/list."""
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    resp = await mcp.handle_message(req, user=readonly_user)
    assert resp["id"] == 2
    tools = resp["result"]["tools"]
    assert len(tools) >= 10
    tool_names = [t["name"] for t in tools]
    assert "get_system_metrics" in tool_names
    assert "list_containers" in tool_names
    assert "restart_service" in tool_names


@pytest.mark.asyncio
async def test_tools_call_execution(mcp, readonly_user):
    """Test successful tool execution."""
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_system_metrics",
            "arguments": {},
        },
    }
    resp = await mcp.handle_message(req, user=readonly_user)
    assert resp["id"] == 3
    result = resp["result"]
    assert result["isError"] is False
    assert len(result["content"]) > 0
    assert result["content"][0]["type"] == "text"
    assert "cpu" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_method_not_found(mcp):
    """Test method not found error (-32601)."""
    req = {"jsonrpc": "2.0", "id": 4, "method": "non_existent_method"}
    resp = await mcp.handle_message(req)
    assert resp["id"] == 4
    assert resp["error"]["code"] == JSONRPCErrorCode.METHOD_NOT_FOUND.value


@pytest.mark.asyncio
async def test_invalid_json_rpc_envelope(mcp):
    """Test invalid JSON-RPC envelope (-32600)."""
    req = {"id": 5}  # missing jsonrpc and method
    resp = await mcp.handle_message(req)
    assert resp["error"]["code"] == JSONRPCErrorCode.INVALID_REQUEST.value


@pytest.mark.asyncio
async def test_batch_requests(mcp, readonly_user):
    """Test standard JSON-RPC 2.0 batch execution."""
    batch = [
        {"jsonrpc": "2.0", "id": 10, "method": "ping"},
        {"jsonrpc": "2.0", "id": 11, "method": "tools/list"},
    ]
    resp = await mcp.handle_message(batch, user=readonly_user)
    assert isinstance(resp, list)
    assert len(resp) == 2
    assert resp[0]["id"] == 10
    assert resp[1]["id"] == 11


@pytest.mark.asyncio
async def test_resources_and_prompts(mcp):
    """Test resources and prompt templates."""
    # List resources
    resp = await mcp.handle_message({"jsonrpc": "2.0", "id": 20, "method": "resources/list"})
    resources = resp["result"]["resources"]
    assert any(r["uri"] == "nexusops://system/metrics" for r in resources)

    # Read resource
    resp = await mcp.handle_message({
        "jsonrpc": "2.0",
        "id": 21,
        "method": "resources/read",
        "params": {"uri": "nexusops://system/metrics"},
    })
    assert len(resp["result"]["contents"]) > 0

    # Prompts
    resp = await mcp.handle_message({"jsonrpc": "2.0", "id": 22, "method": "prompts/list"})
    assert len(resp["result"]["prompts"]) > 0
