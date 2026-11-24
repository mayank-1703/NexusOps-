"""Unit tests for tool schema introspection and execution."""

import json
import pytest
from nexusops.mock.mock_infra import mock_infra
from nexusops.security.rbac import Role, UserContext
from nexusops.tools.registry import tool_registry


@pytest.fixture(autouse=True)
def reset_infra():
    mock_infra.reset()


@pytest.fixture
def admin_user():
    return UserContext(identity="admin-tester", role=Role.ADMIN)


@pytest.fixture
def operator_user():
    return UserContext(identity="operator-tester", role=Role.OPERATOR)


@pytest.mark.asyncio
async def test_container_tools(operator_user):
    """Test listing and inspecting containers."""
    res = await tool_registry.execute("list_containers", {"all_containers": True}, user=operator_user)
    assert res.isError is False
    containers = json.loads(res.content[0].text)
    assert len(containers) >= 4

    # Inspect
    res_inspect = await tool_registry.execute(
        "inspect_container", {"container_id_or_name": "nexus-redis-cache"}, user=operator_user
    )
    assert res_inspect.isError is False
    details = json.loads(res_inspect.content[0].text)
    assert details["name"] == "nexus-redis-cache"


@pytest.mark.asyncio
async def test_log_analysis_tool(operator_user):
    """Test log anomaly detection."""
    res = await tool_registry.execute(
        "analyze_service_logs", {"container_id_or_name": "nexus-redis-cache"}, user=operator_user
    )
    assert res.isError is False
    analysis = json.loads(res.content[0].text)
    assert analysis["total_anomalies_detected"] > 0
    assert analysis["health_assessment"] in ("CRITICAL", "DEGRADED")
    assert "flush_cache" in analysis["recommended_remediation"]


@pytest.mark.asyncio
async def test_remediation_flush_cache(operator_user):
    """Test cache flush remediation."""
    res = await tool_registry.execute("flush_cache", {}, user=operator_user)
    assert res.isError is False
    data = json.loads(res.content[0].text)
    assert data["result"]["status"] == "success"
    assert data["result"]["freed_keys"] > 0
