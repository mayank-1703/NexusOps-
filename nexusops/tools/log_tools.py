"""Service log analysis, anomaly detection, and automated diagnostics tools."""

import re
import time
from typing import Any, Dict, List, Optional
from nexusops.mock.mock_infra import mock_infra
from nexusops.security.rbac import Role, SafetyTier
from nexusops.tools.base import mcp_tool


ERROR_PATTERNS = [
    (r"(?i)connectionrefusederror|unable to reach", "DATABASE_OR_UPSTREAM_DISCONNECT", "HIGH"),
    (r"(?i)out of memory|oom|maxmemory-policy", "OUT_OF_MEMORY", "CRITICAL"),
    (r"(?i)crashloopbackoff|fatal", "SERVICE_CRASH_LOOP", "CRITICAL"),
    (r"(?i)timeout|timed out", "REQUEST_TIMEOUT", "MEDIUM"),
    (r"(?i)threshold|high request rate", "HIGH_RESOURCE_PRESSURE", "LOW"),
]


@mcp_tool(
    name="analyze_service_logs",
    description="Scan and analyze recent logs of a service for errors, tracebacks, anomalies, and root-cause patterns.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def analyze_service_logs(container_id_or_name: str, max_lines: int = 100) -> Dict[str, Any]:
    """Perform automated log regex matching and anomaly extraction."""
    container = mock_infra.inspect_container(container_id_or_name)
    if not container:
        raise ValueError(f"Service or container '{container_id_or_name}' not found.")

    logs = container.get("logs", [])[-max_lines:]
    anomalies: List[Dict[str, Any]] = []

    for idx, line in enumerate(logs):
        for pattern, category, severity in ERROR_PATTERNS:
            if re.search(pattern, line):
                anomalies.append(
                    {
                        "line_index": idx + 1,
                        "raw_log": line,
                        "category": category,
                        "severity": severity,
                    }
                )

    has_critical = any(a["severity"] == "CRITICAL" for a in anomalies)
    has_high = any(a["severity"] == "HIGH" for a in anomalies)

    recommended_action = "none"
    if any(a["category"] == "OUT_OF_MEMORY" for a in anomalies):
        recommended_action = "flush_cache or scale_service"
    elif any(a["category"] in ("SERVICE_CRASH_LOOP", "DATABASE_OR_UPSTREAM_DISCONNECT") for a in anomalies):
        recommended_action = "restart_service"

    return {
        "service": container["name"],
        "analyzed_lines": len(logs),
        "total_anomalies_detected": len(anomalies),
        "anomalies": anomalies,
        "health_assessment": "CRITICAL" if has_critical else ("DEGRADED" if has_high else "HEALTHY"),
        "recommended_remediation": recommended_action,
    }


@mcp_tool(
    name="check_service_health",
    description="Evaluate operational health, metrics, and failure indicators for a managed infrastructure component.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def check_service_health(container_id_or_name: str) -> Dict[str, Any]:
    """Run synthetic health checks and diagnostic status against a service."""
    container = mock_infra.inspect_container(container_id_or_name)
    if not container:
        raise ValueError(f"Service '{container_id_or_name}' not found.")

    status = container.get("status")
    health = container.get("health")
    cpu = container.get("cpu_percent", 0.0)
    mem_mb = container.get("memory_mb", 0.0)

    is_healthy = status == "running" and health == "healthy" and cpu < 80.0

    diagnosis = "Service operating normally."
    if status == "error":
        diagnosis = "Service has crashed or is in backoff loop."
    elif health == "unhealthy":
        diagnosis = f"Service health checks failing. High memory ({mem_mb}MB) or CPU ({cpu}%)."

    return {
        "service": container["name"],
        "status": status,
        "health": health,
        "is_healthy": is_healthy,
        "cpu_percent": cpu,
        "memory_mb": mem_mb,
        "restart_count": container.get("restart_count", 0),
        "diagnosis": diagnosis,
    }
