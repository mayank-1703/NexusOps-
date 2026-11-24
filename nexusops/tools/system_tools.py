"""Host & system monitoring tools using psutil."""

import socket
import time
from typing import Any, Dict, List
import psutil
from nexusops.security.rbac import Role, SafetyTier
from nexusops.tools.base import mcp_tool


@mcp_tool(
    name="get_system_metrics",
    description="Retrieve live CPU, memory, disk, and network metrics for the host infrastructure.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def get_system_metrics() -> Dict[str, Any]:
    """Retrieve live host system performance metrics."""
    cpu_percent = psutil.cpu_percent(interval=0.2)
    cpu_count = psutil.cpu_count(logical=True)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    return {
        "timestamp": time.time(),
        "cpu": {
            "percent": cpu_percent,
            "core_count": cpu_count,
        },
        "memory": {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent_mb": round(net.bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(net.bytes_recv / (1024**2), 2),
        },
    }


@mcp_tool(
    name="list_active_processes",
    description="List top processes on the host sorted by CPU or memory usage.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def list_active_processes(limit: int = 10, sort_by: str = "cpu") -> List[Dict[str, Any]]:
    """List active processes with resource consumption statistics."""
    processes = []
    for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            processes.append(
                {
                    "pid": info["pid"],
                    "name": info["name"],
                    "user": info.get("username", "unknown"),
                    "cpu_percent": info.get("cpu_percent") or 0.0,
                    "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    sort_key = "memory_percent" if sort_by.lower() == "memory" else "cpu_percent"
    processes.sort(key=lambda p: p.get(sort_key, 0), reverse=True)
    return processes[:limit]


@mcp_tool(
    name="probe_network_port",
    description="Perform a TCP socket probe against a target host and port to verify network connectivity.",
    required_role=Role.READONLY,
    safety_tier=SafetyTier.SAFE,
)
def probe_network_port(host: str, port: int, timeout_seconds: float = 3.0) -> Dict[str, Any]:
    """Test TCP network connectivity to a remote or local address."""
    start_time = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    try:
        sock.connect((host, port))
        sock.close()
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "host": host,
            "port": port,
            "status": "OPEN",
            "latency_ms": latency_ms,
            "reachable": True,
        }
    except Exception as exc:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "host": host,
            "port": port,
            "status": "CLOSED_OR_FILTERED",
            "latency_ms": latency_ms,
            "reachable": False,
            "error": str(exc),
        }
