"""Infrastructure remediation tools with RBAC and Human-in-the-Loop protection."""

from typing import Any, Dict
from nexusops.mock.mock_infra import mock_infra
from nexusops.security.rbac import Role, SafetyTier
from nexusops.tools.base import mcp_tool


@mcp_tool(
    name="restart_service",
    description="Restart a service or container to recover from transient crashes or errors.",
    required_role=Role.OPERATOR,
    safety_tier=SafetyTier.MODERATE,
    requires_approval=False,
)
def restart_service(service_name: str) -> Dict[str, Any]:
    """Gracefully restart a container or service."""
    result = mock_infra.restart_container(service_name)
    return {
        "action": "restart_service",
        "service": service_name,
        "status": "RESTARTED",
        "details": result,
    }


@mcp_tool(
    name="scale_service",
    description="Scale a service to a specified replica count to handle workload demand.",
    required_role=Role.OPERATOR,
    safety_tier=SafetyTier.MODERATE,
    requires_approval=False,
)
def scale_service(service_name: str, replicas: int) -> Dict[str, Any]:
    """Adjust replica count for a target service."""
    result = mock_infra.scale_service(service_name, replicas)
    return {
        "action": "scale_service",
        "result": result,
    }


@mcp_tool(
    name="flush_cache",
    description="Flush volatile in-memory cache to resolve Out-of-Memory (OOM) conditions.",
    required_role=Role.OPERATOR,
    safety_tier=SafetyTier.MODERATE,
    requires_approval=False,
)
def flush_cache() -> Dict[str, Any]:
    """Clear memory keys in redis cache."""
    result = mock_infra.flush_redis_cache()
    return {
        "action": "flush_cache",
        "result": result,
    }


@mcp_tool(
    name="terminate_container",
    description="Forcefully stop and terminate a container. Destructive action requiring Human-in-the-Loop approval.",
    required_role=Role.ADMIN,
    safety_tier=SafetyTier.CRITICAL,
    requires_approval=True,
)
def terminate_container(container_id_or_name: str) -> Dict[str, Any]:
    """Terminate a container instance. Protected by HITL approval."""
    result = mock_infra.stop_container(container_id_or_name)
    return {
        "action": "terminate_container",
        "container": container_id_or_name,
        "status": "TERMINATED",
        "details": result,
    }


@mcp_tool(
    name="prune_system_resources",
    description="Prune dangling images, unused volumes, and stopped containers to free disk. Requires HITL approval.",
    required_role=Role.ADMIN,
    safety_tier=SafetyTier.CRITICAL,
    requires_approval=True,
)
def prune_system_resources(prune_volumes: bool = False) -> Dict[str, Any]:
    """Prune unused system and container resources. Protected by HITL approval."""
    return {
        "action": "prune_system_resources",
        "volumes_pruned": prune_volumes,
        "space_reclaimed_gb": 4.8,
        "status": "COMPLETED",
    }
