"""Container lifecycle and inspection tools."""

from typing import Any, Dict, List, Optional
from nexusops.config import settings
from nexusops.mock.mock_infra import mock_infra
from nexusops.security.rbac import Role, SafetyTier
from nexusops.tools.base import mcp_tool


@mcp_tool(
    name="list_containers",
    description="List all infrastructure containers, their statuses, health checks, and resource usage.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def list_containers(all_containers: bool = True) -> List[Dict[str, Any]]:
    """Enumerate managed containers and their current state."""
    # Uses mock infrastructure engine (which simulates real Docker daemon containers)
    containers = mock_infra.list_containers()
    if not all_containers:
        containers = [c for c in containers if c["status"] == "running"]
    return containers


@mcp_tool(
    name="inspect_container",
    description="Retrieve deep configuration, port bindings, and runtime health for a container by name or ID.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def inspect_container(container_id_or_name: str) -> Dict[str, Any]:
    """Inspect detailed state of a specific container."""
    details = mock_infra.inspect_container(container_id_or_name)
    if not details:
        raise ValueError(f"Container '{container_id_or_name}' not found.")
    return details


@mcp_tool(
    name="get_container_logs",
    description="Fetch recent stdout/stderr log lines for a specific container.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def get_container_logs(container_id_or_name: str, tail: int = 50) -> Dict[str, Any]:
    """Retrieve tail logs for debugging and analysis."""
    details = mock_infra.inspect_container(container_id_or_name)
    if not details:
        raise ValueError(f"Container '{container_id_or_name}' not found.")

    logs = details.get("logs", [])
    selected_logs = logs[-tail:] if tail > 0 else logs

    return {
        "container": details["name"],
        "id": details["id"],
        "line_count": len(selected_logs),
        "logs": selected_logs,
    }
