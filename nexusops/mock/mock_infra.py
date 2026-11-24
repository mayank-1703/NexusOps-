"""Mock infrastructure state and simulator for local development, demos, and testing."""

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ContainerState(BaseModel):
    """Simulated container entity."""

    id: str
    name: str
    image: str
    status: str  # running, stopped, restarting, error
    health: str  # healthy, unhealthy, starting
    cpu_percent: float
    memory_mb: float
    restart_count: int = 0
    created_at: float = 0.0
    ports: Dict[str, str] = {}
    logs: List[str] = []


class MockInfrastructure:
    """In-memory realistic infrastructure engine simulating microservices and containers."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset mock infrastructure to initial default state."""
        now = time.time()
        self.containers: Dict[str, ContainerState] = {
            "cnt-gateway-01": ContainerState(
                id="cnt-gateway-01",
                name="nexus-api-gateway",
                image="nginx:1.25-alpine",
                status="running",
                health="healthy",
                cpu_percent=12.4,
                memory_mb=128.5,
                ports={"80/tcp": "8080", "443/tcp": "8443"},
                created_at=now - 3600 * 24,
                logs=[
                    "[2026-11-19 10:00:12] [INFO] Configuration reloaded successfully.",
                    "[2026-11-19 10:15:33] [INFO] Upstream health check OK for backend cluster.",
                    "[2026-11-19 10:30:00] [WARN] High request rate detected on /api/v1/metrics (1420 req/s).",
                ],
            ),
            "cnt-redis-01": ContainerState(
                id="cnt-redis-01",
                name="nexus-redis-cache",
                image="redis:7.2-alpine",
                status="running",
                health="unhealthy",
                cpu_percent=88.7,
                memory_mb=1850.0,
                ports={"6379/tcp": "6379"},
                created_at=now - 3600 * 48,
                logs=[
                    "[2026-11-19 10:20:00] [INFO] Ready to accept connections.",
                    "[2026-11-19 10:32:15] [WARN] Memory usage exceeds 85% threshold (1.85GB / 2.0GB).",
                    "[2026-11-19 10:35:44] [ERROR] OOM command rejected: maxmemory-policy volatile-lru unable to free keys.",
                    "[2026-11-19 10:36:01] [ERROR] Client connection pool exhausted; queue depth=450.",
                ],
            ),
            "cnt-auth-01": ContainerState(
                id="cnt-auth-01",
                name="nexus-auth-service",
                image="nexusops/auth-service:v2.1.0",
                status="error",
                health="unhealthy",
                cpu_percent=0.0,
                memory_mb=45.0,
                restart_count=5,
                ports={"5000/tcp": "5000"},
                created_at=now - 3600 * 12,
                logs=[
                    "[2026-11-19 10:10:00] [INFO] Service initialized on port 5000.",
                    "[2026-11-19 10:25:12] [ERROR] ConnectionRefusedError: Unable to reach auth DB cluster at db:5432.",
                    "[2026-11-19 10:25:15] [FATAL] Process exiting with status 1: Fatal DB connection failure.",
                    "[2026-11-19 10:26:00] [INFO] Container restarted (restart count: 5).",
                    "[2026-11-19 10:26:05] [FATAL] CrashLoopBackOff: backoff 5m0s restarting failed container.",
                ],
            ),
            "cnt-postgres-01": ContainerState(
                id="cnt-postgres-01",
                name="nexus-postgres-db",
                image="postgres:16-alpine",
                status="running",
                health="healthy",
                cpu_percent=24.1,
                memory_mb=512.0,
                ports={"5432/tcp": "5432"},
                created_at=now - 3600 * 72,
                logs=[
                    "[2026-11-19 08:00:00] [INFO] PostgreSQL Database directory appearance: ok",
                    "[2026-11-19 08:00:01] [INFO] database system is ready to accept connections",
                    "[2026-11-19 10:30:11] [INFO] checkpoint starting: time",
                    "[2026-11-19 10:30:14] [INFO] checkpoint complete: wrote 842 buffers (5.1%); 0 WAL file(s) added",
                ],
            ),
        }
        self.cached_keys_count = 1450200
        self.services_scaled = {"nexus-worker": 2}

    def list_containers(self) -> List[Dict[str, Any]]:
        return [c.model_dump() for c in self.containers.values()]

    def inspect_container(self, container_id_or_name: str) -> Optional[Dict[str, Any]]:
        for c in self.containers.values():
            if c.id == container_id_or_name or c.name == container_id_or_name:
                return c.model_dump()
        return None

    def restart_container(self, container_id_or_name: str) -> Dict[str, Any]:
        c = self._find_container(container_id_or_name)
        if not c:
            raise ValueError(f"Container '{container_id_or_name}' not found.")
        c.status = "running"
        c.health = "healthy"
        c.restart_count += 1
        c.cpu_percent = 5.0
        c.logs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Container restarted via NexusOps control plane.")
        return {"id": c.id, "name": c.name, "status": c.status, "health": c.health, "restart_count": c.restart_count}

    def stop_container(self, container_id_or_name: str) -> Dict[str, Any]:
        c = self._find_container(container_id_or_name)
        if not c:
            raise ValueError(f"Container '{container_id_or_name}' not found.")
        c.status = "stopped"
        c.health = "unhealthy"
        c.cpu_percent = 0.0
        c.logs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Container gracefully stopped via NexusOps.")
        return {"id": c.id, "name": c.name, "status": c.status}

    def flush_redis_cache(self) -> Dict[str, Any]:
        c = self.containers.get("cnt-redis-01")
        if c:
            c.memory_mb = 120.0
            c.cpu_percent = 4.2
            c.health = "healthy"
            c.logs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] FLUSHALL command executed. Freed {self.cached_keys_count} keys.")
        freed = self.cached_keys_count
        self.cached_keys_count = 0
        return {"status": "success", "freed_keys": freed, "memory_freed_mb": 1730.0}

    def scale_service(self, service_name: str, replicas: int) -> Dict[str, Any]:
        if replicas < 0 or replicas > 20:
            raise ValueError("Replicas must be between 0 and 20.")
        old = self.services_scaled.get(service_name, 1)
        self.services_scaled[service_name] = replicas
        return {"service": service_name, "previous_replicas": old, "target_replicas": replicas, "status": "scaled"}

    def _find_container(self, query: str) -> Optional[ContainerState]:
        for c in self.containers.values():
            if c.id == query or c.name == query:
                return c
        return None


# Global mock infrastructure singleton
mock_infra = MockInfrastructure()
