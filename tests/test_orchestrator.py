"""Unit tests for multi-server orchestrator, concurrent execution, and fault isolation."""

import asyncio
import pytest
from nexusops.orchestrator.engine import (
    ToolExecutionTask,
    orchestrator,
)
from nexusops.orchestrator.fault_isolation import (
    CircuitBreaker,
    CircuitState,
    FaultIsolationBoundary,
)
from nexusops.security.rbac import Role, UserContext


@pytest.fixture
def admin_user():
    return UserContext(identity="admin-agent", role=Role.ADMIN)


@pytest.mark.asyncio
async def test_concurrent_plan_execution(admin_user):
    """Test concurrent execution of multiple infrastructure operations."""
    tasks = [
        ToolExecutionTask(tool_name="get_system_metrics", arguments={}),
        ToolExecutionTask(tool_name="list_containers", arguments={"all_containers": True}),
        ToolExecutionTask(
            tool_name="check_service_health",
            arguments={"container_id_or_name": "nexus-api-gateway"},
        ),
    ]

    report = await orchestrator.execute_concurrent_plan(tasks, user=admin_user)
    assert report.total_tasks == 3
    assert report.successful_tasks == 3
    assert report.failed_tasks == 0
    assert len(report.results) == 3


@pytest.mark.asyncio
async def test_fault_isolation_in_batch(admin_user):
    """Test fault isolation: one failing tool does not disrupt other tasks."""
    tasks = [
        ToolExecutionTask(tool_name="get_system_metrics", arguments={}),
        ToolExecutionTask(
            tool_name="inspect_container",
            arguments={"container_id_or_name": "non_existent_container"},  # Will fail
        ),
        ToolExecutionTask(tool_name="list_containers", arguments={}),
    ]

    report = await orchestrator.execute_concurrent_plan(tasks, user=admin_user)
    assert report.total_tasks == 3
    assert report.successful_tasks == 2  # The 2 healthy tasks still succeed!
    assert report.failed_tasks == 1

    # Verify failure isolation
    failed_result = next(r for r in report.results if not r["success"])
    assert failed_result["tool_name"] == "inspect_container"
    assert "not found" in str(failed_result["output"] or failed_result["error"])


@pytest.mark.asyncio
async def test_circuit_breaker_tripping():
    """Test circuit breaker transitions from CLOSED to OPEN after repeated failures."""
    cb = CircuitBreaker(name="test-node", failure_threshold=2, recovery_timeout_seconds=0.1)
    boundary = FaultIsolationBoundary(target_name="test-node", circuit_breaker=cb, max_retries=0)

    def failing_action():
        raise ConnectionResetError("Connection refused by peer node")

    # Attempt 1
    res1 = await boundary.execute(failing_action)
    assert res1["success"] is False
    assert cb.state == CircuitState.CLOSED

    # Attempt 2 -> Reaches failure threshold 2 -> TRIPS
    res2 = await boundary.execute(failing_action)
    assert res2["success"] is False
    assert cb.state == CircuitState.OPEN

    # Attempt 3 -> Fails fast due to OPEN circuit breaker
    res3 = await boundary.execute(failing_action)
    assert res3["success"] is False
    assert "Circuit breaker OPEN" in res3["error"]

    # Wait for recovery timeout
    await asyncio.sleep(0.15)
    assert await cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN
