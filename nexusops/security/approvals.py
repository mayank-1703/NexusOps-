"""Human-in-the-Loop (HITL) Approval Engine for NexusOps."""

import asyncio
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from nexusops.config import settings
from nexusops.security.rbac import Role, SafetyTier, UserContext


class ApprovalStatus(str, Enum):
    """Lifecycle status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"


class ApprovalRequest(BaseModel):
    """Structured request for human approval before executing risky operations."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    arguments: Dict[str, Any]
    requester: str
    requester_role: Role
    safety_tier: SafetyTier
    reason: str
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    decision_by: Optional[str] = None
    decision_at: Optional[float] = None
    decision_note: Optional[str] = None
    execution_result: Optional[Any] = None

    @property
    def is_expired(self) -> bool:
        return self.status == ApprovalStatus.PENDING and time.time() > self.expires_at


class ApprovalManager:
    """Manages pending human-in-the-loop approvals with asyncio event notifications."""

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    def create_request(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user: UserContext,
        safety_tier: SafetyTier,
        reason: str,
        timeout_seconds: Optional[int] = None,
    ) -> ApprovalRequest:
        """Create and register a new approval request."""
        ttl = timeout_seconds or settings.approval_timeout_seconds
        req = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            requester=user.identity,
            requester_role=user.role,
            safety_tier=safety_tier,
            reason=reason,
            expires_at=time.time() + ttl,
        )
        self._requests[req.id] = req
        self._events[req.id] = asyncio.Event()
        return req

    async def approve_request(
        self, request_id: str, approver: str, note: Optional[str] = None
    ) -> ApprovalRequest:
        """Approve a pending request."""
        async with self._lock:
            req = self.get_request(request_id)
            if not req:
                raise ValueError(f"Approval request {request_id} not found.")
            if req.is_expired:
                req.status = ApprovalStatus.EXPIRED
                raise ValueError(f"Approval request {request_id} has expired.")
            if req.status != ApprovalStatus.PENDING:
                raise ValueError(f"Approval request {request_id} is already {req.status}.")

            req.status = ApprovalStatus.APPROVED
            req.decision_by = approver
            req.decision_at = time.time()
            req.decision_note = note or "Approved by operator/admin"

            # Wake up any awaiting coroutine
            if request_id in self._events:
                self._events[request_id].set()

            return req

    async def reject_request(
        self, request_id: str, approver: str, note: Optional[str] = None
    ) -> ApprovalRequest:
        """Reject a pending request."""
        async with self._lock:
            req = self.get_request(request_id)
            if not req:
                raise ValueError(f"Approval request {request_id} not found.")
            if req.is_expired:
                req.status = ApprovalStatus.EXPIRED
                raise ValueError(f"Approval request {request_id} has expired.")
            if req.status != ApprovalStatus.PENDING:
                raise ValueError(f"Approval request {request_id} is already {req.status}.")

            req.status = ApprovalStatus.REJECTED
            req.decision_by = approver
            req.decision_at = time.time()
            req.decision_note = note or "Rejected by human reviewer"

            if request_id in self._events:
                self._events[request_id].set()

            return req

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Fetch request by ID, updating expired status if applicable."""
        req = self._requests.get(request_id)
        if req and req.is_expired:
            req.status = ApprovalStatus.EXPIRED
        return req

    def list_requests(
        self, status: Optional[ApprovalStatus] = None, limit: int = 50
    ) -> List[ApprovalRequest]:
        """List requests, optionally filtered by status."""
        results = []
        for req in reversed(list(self._requests.values())):
            if req.is_expired:
                req.status = ApprovalStatus.EXPIRED
            if status is None or req.status == status:
                results.append(req)
            if len(results) >= limit:
                break
        return results

    async def wait_for_decision(
        self, request_id: str, timeout: Optional[float] = None
    ) -> ApprovalRequest:
        """Wait asynchronously until a decision is recorded or timeout expires."""
        event = self._events.get(request_id)
        if not event:
            raise ValueError(f"No event found for request {request_id}")

        req = self.get_request(request_id)
        if not req:
            raise ValueError(f"Approval request {request_id} not found")

        if req.status != ApprovalStatus.PENDING:
            return req

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            req.status = ApprovalStatus.EXPIRED

        return req

    def mark_executed(self, request_id: str, result: Any):
        """Mark request as successfully executed with its result."""
        req = self.get_request(request_id)
        if req:
            req.status = ApprovalStatus.EXECUTED
            req.execution_result = result


# Global approval manager instance
approval_manager = ApprovalManager()
