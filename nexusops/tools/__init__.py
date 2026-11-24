"""Infrastructure tools registration package."""

from nexusops.tools.base import mcp_tool, extract_json_schema, format_tool_result
from nexusops.tools.registry import tool_registry
from nexusops.tools.system_tools import get_system_metrics, list_active_processes, probe_network_port
from nexusops.tools.container_tools import list_containers, inspect_container, get_container_logs
from nexusops.tools.log_tools import analyze_service_logs, check_service_health
from nexusops.tools.remediation_tools import (
    restart_service,
    scale_service,
    flush_cache,
    terminate_container,
    prune_system_resources,
)


def register_all_tools():
    """Register all built-in tools into the global tool registry."""
    tool_registry.register(get_system_metrics)
    tool_registry.register(list_active_processes)
    tool_registry.register(probe_network_port)

    tool_registry.register(list_containers)
    tool_registry.register(inspect_container)
    tool_registry.register(get_container_logs)

    tool_registry.register(analyze_service_logs)
    tool_registry.register(check_service_health)

    tool_registry.register(restart_service)
    tool_registry.register(scale_service)
    tool_registry.register(flush_cache)
    tool_registry.register(terminate_container)
    tool_registry.register(prune_system_resources)


# Auto-register on import
register_all_tools()

__all__ = [
    "tool_registry",
    "mcp_tool",
    "register_all_tools",
    "format_tool_result",
]
