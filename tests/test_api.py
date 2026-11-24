"""Integration tests for FastAPI REST and MCP endpoints."""

import pytest
import httpx
from httpx import ASGITransport
from nexusops.config import settings
from nexusops.web.app import app


@pytest.mark.asyncio
async def test_api_status():
    """Test /api/status endpoint."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["server_name"] == settings.server_name
        assert data["total_tools"] >= 10


@pytest.mark.asyncio
async def test_mcp_http_endpoint():
    """Test POST /mcp endpoint with JSON-RPC 2.0."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "test-call-1",
            "method": "tools/call",
            "params": {
                "name": "get_system_metrics",
                "arguments": {},
            },
        }
        resp = await client.post("/mcp", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "test-call-1"
        assert data["result"]["isError"] is False


@pytest.mark.asyncio
async def test_api_approvals_workflow():
    """Test creating and deciding approvals via REST API."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Trigger an approval by calling terminate_container without approval_id
        payload = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "terminate_container",
                "arguments": {"container_id_or_name": "nexus-redis-cache"},
            },
        }
        headers = {"Authorization": f"Bearer {settings.admin_api_key}"}
        resp = await client.post("/mcp", json=payload, headers=headers)
        data = resp.json()
        approval_id = data["result"]["metadata"]["approval_id"]

        # Check approval exists in /api/approvals
        list_resp = await client.get("/api/approvals?status=pending")
        assert list_resp.status_code == 200
        pending_list = list_resp.json()
        assert any(item["id"] == approval_id for item in pending_list)

        # Approve via REST API
        approve_resp = await client.post(
            f"/api/approvals/{approval_id}/approve",
            json={"approver": "sre-lead", "note": "Approved via test"},
            headers=headers,
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
