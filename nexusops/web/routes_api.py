"""REST API endpoints for the NexusOps Control Plane web dashboard."""

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from nexusops.config import settings
from nexusops.mock.mock_infra import mock_infra
from nexusops.orchestrator.engine import (
    BatchExecutionReport,
    ToolExecutionTask,
    orchestrator,
)
from nexusops.protocol.transport_http import get_current_user
from nexusops.security.approvals import (
    ApprovalRequest,
    ApprovalStatus,
    approval_manager,
)
from nexusops.security.audit import AuditLogEntry, audit_logger
from nexusops.security.rbac import Role, UserContext
from nexusops.tools.registry import tool_registry

api_router = APIRouter(prefix="/api", tags=["Control Plane API"])
start_time = time.time()


class ApprovalDecisionPayload(BaseModel):
    approver: str = "human-operator"
    note: Optional[str] = None


class BatchExecutionPayload(BaseModel):
    tasks: List[ToolExecutionTask]


@api_router.get("/status")
async def get_status():
    """Retrieve overall control plane status and uptime."""
    return {
        "server_name": settings.server_name,
        "version": settings.server_version,
        "environment": settings.env,
        "uptime_seconds": round(time.time() - start_time, 1),
        "total_tools": len(tool_registry.get_tool_metadata()),
        "pending_approvals_count": len(approval_manager.list_requests(status=ApprovalStatus.PENDING)),
        "active_nodes": 1 + len(orchestrator.remote_servers),
    }


@api_router.get("/tools")
async def list_tools():
    """List tool definitions with metadata and security tiers."""
    return tool_registry.get_tool_metadata()


@api_router.get("/approvals", response_model=List[ApprovalRequest])
async def list_approvals(status: Optional[ApprovalStatus] = None):
    """List approval requests."""
    return approval_manager.list_requests(status=status)


@api_router.post("/approvals/{request_id}/approve", response_model=ApprovalRequest)
async def approve_request(
    request_id: str,
    payload: ApprovalDecisionPayload,
    user: UserContext = Depends(get_current_user),
):
    """Approve a pending human-in-the-loop action."""
    try:
        approver = payload.approver or user.identity
        req = await approval_manager.approve_request(
            request_id=request_id,
            approver=approver,
            note=payload.note,
        )
        return req
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api_router.post("/approvals/{request_id}/reject", response_model=ApprovalRequest)
async def reject_request(
    request_id: str,
    payload: ApprovalDecisionPayload,
    user: UserContext = Depends(get_current_user),
):
    """Reject a pending human-in-the-loop action."""
    try:
        approver = payload.approver or user.identity
        req = await approval_manager.reject_request(
            request_id=request_id,
            approver=approver,
            note=payload.note,
        )
        return req
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api_router.get("/audit", response_model=List[AuditLogEntry])
async def query_audit_logs(
    tool_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """Query operational audit log records."""
    return audit_logger.query(tool_name=tool_name, status=status, limit=limit)


@api_router.post("/orchestrator/batch", response_model=BatchExecutionReport)
async def run_batch_plan(
    payload: BatchExecutionPayload,
    user: UserContext = Depends(get_current_user),
):
    """Execute a concurrent tool execution plan across targets."""
    return await orchestrator.execute_concurrent_plan(payload.tasks, user=user)


@api_router.get("/infra/containers")
async def get_infrastructure_containers():
    """Get live state of managed containers."""
    return mock_infra.list_containers()


@api_router.post("/infra/reset")
async def reset_mock_infrastructure():
    """Reset mock infrastructure to test failure and remediation workflows."""
    mock_infra.reset()
    return {"status": "infrastructure reset to initial state"}
