"""Unit tests for Human-in-the-Loop approval workflows."""

import json
import pytest
from nexusops.security.approvals import ApprovalStatus, approval_manager
from nexusops.security.rbac import Role, UserContext
from nexusops.tools.registry import tool_registry


@pytest.fixture
def admin_user():
    return UserContext(identity="admin-agent", role=Role.ADMIN)


@pytest.mark.asyncio
async def test_hitl_approval_lifecycle(admin_user):
    """Test full cycle: intercept -> pending -> human approval -> execution."""
    # 1. Invoke critical tool without approval
    res = await tool_registry.execute(
        "terminate_container",
        {"container_id_or_name": "nexus-redis-cache"},
        user=admin_user,
    )
    assert res.isError is False
    data = json.loads(res.content[0].text)
    assert data["status"] == "pending_approval"
    approval_id = data["approval_id"]
    assert approval_id is not None

    # Verify request is recorded as pending in the manager
    req = approval_manager.get_request(approval_id)
    assert req is not None
    assert req.status == ApprovalStatus.PENDING

    # 2. Human operator approves the request
    approved_req = await approval_manager.approve_request(
        request_id=approval_id,
        approver="lead-sre@company.com",
        note="Approved for maintenance",
    )
    assert approved_req.status == ApprovalStatus.APPROVED

    # 3. Invocation with approval_id executes successfully
    exec_res = await tool_registry.execute(
        "terminate_container",
        {"container_id_or_name": "nexus-redis-cache", "approval_id": approval_id},
        user=admin_user,
    )
    assert exec_res.isError is False
    exec_data = json.loads(exec_res.content[0].text)
    assert exec_data["action"] == "terminate_container"
    assert exec_data["status"] == "TERMINATED"

    # Check marked as executed
    final_req = approval_manager.get_request(approval_id)
    assert final_req.status == ApprovalStatus.EXECUTED


@pytest.mark.asyncio
async def test_hitl_rejection_blocks_execution(admin_user):
    """Test human rejection cleanly prevents action execution."""
    res = await tool_registry.execute(
        "prune_system_resources",
        {"prune_volumes": True},
        user=admin_user,
    )
    data = json.loads(res.content[0].text)
    approval_id = data["approval_id"]

    # Human rejects
    await approval_manager.reject_request(
        request_id=approval_id,
        approver="security-auditor",
        note="Rejected: Disk cleanup not scheduled.",
    )

    # Attempt to execute with rejected approval_id
    res_rejected = await tool_registry.execute(
        "prune_system_resources",
        {"prune_volumes": True, "approval_id": approval_id},
        user=admin_user,
    )
    assert res_rejected.isError is True
    assert "REJECTED by human operator" in res_rejected.content[0].text
