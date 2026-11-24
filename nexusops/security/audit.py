"""Audit logging for tracking all operations and security events in NexusOps."""

from collections import deque
from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    """Structured audit log record."""

    id: str = Field(default_factory=lambda: f"aud_{int(time.time() * 1000)}")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    requester: str
    role: str
    tool_name: str
    arguments: Dict[str, Any]
    status: str  # SUCCESS, FAILED, PENDING_APPROVAL, REJECTED, EXPIRED
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    approval_id: Optional[str] = None
    result_summary: Optional[str] = None


class AuditLogger:
    """Thread-safe circular audit logger with structured query capabilities."""

    def __init__(self, max_entries: int = 1000):
        self._entries: deque = deque(maxlen=max_entries)

    def log(
        self,
        requester: str,
        role: str,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str,
        duration_ms: float = 0.0,
        error_message: Optional[str] = None,
        approval_id: Optional[str] = None,
        result_summary: Optional[str] = None,
    ) -> AuditLogEntry:
        """Create and store an audit log entry."""
        entry = AuditLogEntry(
            requester=requester,
            role=role,
            tool_name=tool_name,
            arguments=arguments,
            status=status,
            duration_ms=round(duration_ms, 2),
            error_message=error_message,
            approval_id=approval_id,
            result_summary=result_summary,
        )
        self._entries.appendleft(entry)
        return entry

    def query(
        self,
        tool_name: Optional[str] = None,
        status: Optional[str] = None,
        requester: Optional[str] = None,
        limit: int = 50,
    ) -> List[AuditLogEntry]:
        """Query audit log records with filtering."""
        results = []
        for entry in self._entries:
            if tool_name and entry.tool_name != tool_name:
                continue
            if status and entry.status != status:
                continue
            if requester and entry.requester != requester:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def clear(self):
        """Clear audit history (used in testing)."""
        self._entries.clear()


# Global audit logger instance
audit_logger = AuditLogger()
