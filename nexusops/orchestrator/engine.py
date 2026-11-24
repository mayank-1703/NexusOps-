"""Multi-server orchestration engine with concurrent execution and fault isolation."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from nexusops.config import settings
from nexusops.orchestrator.fault_isolation import FaultIsolationBoundary
from nexusops.protocol.models import Tool
from nexusops.security.rbac import Role, UserContext
from nexusops.tools.registry import tool_registry

logger = logging.getLogger("nexusops.orchestrator")


class RemoteServerNode(BaseModel):
    """Configuration for an upstream or peer MCP server."""

    name: str
    url: str  # e.g. http://node-east:8000/mcp
    api_key: Optional[str] = None
    enabled: bool = True


class ToolExecutionTask(BaseModel):
    """Specification for a tool to run in an execution plan."""

    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    target_server: Optional[str] = "local"  # "local" or remote server name
    approval_id: Optional[str] = None


class BatchExecutionReport(BaseModel):
    """Aggregated results of a concurrent multi-tool execution plan."""

    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    total_duration_ms: float
    results: List[Dict[str, Any]]


class MultiServerOrchestrator:
    """Orchestrates tool discovery and concurrent tool execution across local and remote MCP servers."""

    def __init__(self):
        self.remote_servers: Dict[str, RemoteServerNode] = {}
        self.boundaries: Dict[str, FaultIsolationBoundary] = {
            "local": FaultIsolationBoundary(target_name="local-server", timeout_seconds=settings.tool_timeout_seconds)
        }
        self.semaphore = asyncio.Semaphore(settings.orchestrator_concurrency_limit)

    def register_remote_server(self, name: str, url: str, api_key: Optional[str] = None):
        """Register an upstream MCP server node."""
        self.remote_servers[name] = RemoteServerNode(name=name, url=url, api_key=api_key)
        self.boundaries[name] = FaultIsolationBoundary(
            target_name=f"remote-{name}",
            timeout_seconds=settings.tool_timeout_seconds,
        )

    async def aggregate_tools(self, user: Optional[UserContext] = None) -> List[Tool]:
        """Aggregate tools across the local registry and all healthy remote MCP servers."""
        local_tools = tool_registry.list_tools(user)
        all_tools = list(local_tools)

        for name, node in self.remote_servers.items():
            if not node.enabled:
                continue

            boundary = self.boundaries.get(name)
            if not boundary:
                continue

            async def fetch_remote_tools():
                headers = {}
                if node.api_key:
                    headers["Authorization"] = f"Bearer {node.api_key}"

                async with httpx.AsyncClient(timeout=5.0) as client:
                    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                    resp = await client.post(node.url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("result", {}).get("tools", [])

            call_res = await boundary.execute(fetch_remote_tools)
            if call_res.get("success"):
                for t in call_res["result"]:
                    # Prefix tool name with node name for namespace isolation
                    all_tools.append(
                        Tool(
                            name=f"{name}::{t['name']}",
                            description=f"[{name.upper()}] {t.get('description', '')}",
                            inputSchema=t.get("inputSchema", {}),
                        )
                    )
            else:
                logger.warning("Failed to aggregate tools from remote node '%s': %s", name, call_res.get("error"))

        return all_tools

    async def execute_task(self, task: ToolExecutionTask, user: UserContext) -> Dict[str, Any]:
        """Execute a single tool task wrapped in concurrency limits and fault isolation."""
        async with self.semaphore:
            target = task.target_server or "local"
            boundary = self.boundaries.get(target) or self.boundaries["local"]

            async def _run():
                if target == "local":
                    res = await tool_registry.execute(
                        name=task.tool_name,
                        arguments=task.arguments,
                        user=user,
                        approval_id=task.approval_id,
                    )
                    return res.model_dump()
                else:
                    node = self.remote_servers.get(target)
                    if not node:
                        raise ValueError(f"Remote server '{target}' not registered.")

                    headers = {}
                    if node.api_key:
                        headers["Authorization"] = f"Bearer {node.api_key}"

                    async with httpx.AsyncClient(timeout=settings.tool_timeout_seconds) as client:
                        payload = {
                            "jsonrpc": "2.0",
                            "id": int(time.time()),
                            "method": "tools/call",
                            "params": {
                                "name": task.tool_name,
                                "arguments": task.arguments,
                            },
                        }
                        resp = await client.post(node.url, json=payload, headers=headers)
                        resp.raise_for_status()
                        return resp.json().get("result", {})

            isolation_result = await boundary.execute(_run)

            # Check if the tool execution itself reported an error (isError=True)
            res_payload = isolation_result.get("result")
            is_tool_error = False
            if isinstance(res_payload, dict):
                is_tool_error = res_payload.get("isError", False)

            overall_success = isolation_result.get("success", False) and not is_tool_error
            error_msg = isolation_result.get("error")
            if is_tool_error and not error_msg and res_payload.get("content"):
                error_msg = res_payload["content"][0].get("text")

            return {
                "tool_name": task.tool_name,
                "target": target,
                "arguments": task.arguments,
                "success": overall_success,
                "duration_ms": isolation_result.get("duration_ms", 0.0),
                "circuit_state": isolation_result.get("circuit_state"),
                "output": res_payload if overall_success else None,
                "error": error_msg,
            }

    async def execute_concurrent_plan(
        self,
        tasks: List[ToolExecutionTask],
        user: UserContext,
    ) -> BatchExecutionReport:
        """Execute multiple infrastructure tool tasks concurrently with fault isolation."""
        start_time = time.time()
        coroutines = [self.execute_task(task, user) for task in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=False)

        total_duration = (time.time() - start_time) * 1000
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful

        return BatchExecutionReport(
            total_tasks=len(tasks),
            successful_tasks=successful,
            failed_tasks=failed,
            total_duration_ms=round(total_duration, 2),
            results=results,
        )


# Global orchestrator instance
orchestrator = MultiServerOrchestrator()
