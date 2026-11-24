"""Autonomous AI Agent Demonstration Client for NexusOps.

Simulates an autonomous SRE agent communicating with NexusOps over Model Context Protocol (MCP)
via JSON-RPC 2.0 to triage incidents, analyze logs, and safely remediate infrastructure.
"""

import asyncio
import json
from pathlib import Path
import sys
import time
import httpx

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SERVER_URL = "http://127.0.0.1:8000/mcp"
OPERATOR_KEY = "nexus-operator-secret-key-67890"
ADMIN_KEY = "nexus-admin-secret-key-12345"


class AutonomousAgentClient:
    """Client implementing MCP JSON-RPC 2.0 protocol communication."""

    def __init__(self, base_url: str = SERVER_URL, api_key: str = OPERATOR_KEY):
        self.base_url = base_url
        self.api_key = api_key
        self.req_id = 1

    async def send_rpc(self, method: str, params: dict = None) -> dict:
        """Send a JSON-RPC 2.0 request and return the result."""
        payload = {
            "jsonrpc": "2.0",
            "id": self.req_id,
            "method": method,
            "params": params or {},
        }
        self.req_id += 1

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self.base_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            # Fallback to direct in-memory ASGI transport if port/network is unavailable
            from httpx import ASGITransport
            from nexusops.web.app import app

            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://local-mcp") as client:
                resp = await client.post("/mcp", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

        if "error" in data:
            raise RuntimeError(f"RPC Error [{data['error']['code']}]: {data['error']['message']}")
        return data.get("result")

    async def initialize(self):
        """Negotiate capabilities with NexusOps MCP server."""
        print("\n[1] Capability Negotiation (initialize)...")
        result = await self.send_rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {}},
                "clientInfo": {"name": "NexusAutonomousAgent", "version": "1.0"},
            },
        )
        print(f"  Connected to: {result['serverInfo']['name']} (v{result['serverInfo']['version']})")
        print(f"  Server Capabilities: {list(result['capabilities'].keys())}")

    async def discover_tools(self):
        """Dynamic tool discovery."""
        print("\n[2] Dynamic Tool Discovery (tools/list)...")
        result = await self.send_rpc("tools/list")
        tools = result.get("tools", [])
        print(f"  Discovered {len(tools)} tools:")
        for t in tools[:5]:
            print(f"   • {t['name']}: {t['description'][:60]}...")
        if len(tools) > 5:
            print(f"   • ... and {len(tools) - 5} more.")

    async def run_autonomous_diagnostic_and_remediation(self):
        """Execute autonomous incident triage and remediation workflow."""
        print("\n[3] Autonomous Infrastructure Triage...")

        # Step 3a: Assess host health
        print("  → Checking system metrics...")
        res = await self.send_rpc("tools/call", {"name": "get_system_metrics", "arguments": {}})
        metrics = json.loads(res["content"][0]["text"])
        print(f"    Host CPU: {metrics['cpu']['percent']}% | Memory: {metrics['memory']['percent']}% used")

        # Step 3b: List containers to spot degraded services
        print("  → Enumerating container health...")
        res = await self.send_rpc("tools/call", {"name": "list_containers", "arguments": {"all_containers": True}})
        containers = json.loads(res["content"][0]["text"])
        unhealthy = [c for c in containers if c["health"] != "healthy"]

        if unhealthy:
            target = unhealthy[0]["name"]
            print(f"    ⚠️ Detected degraded container: {target} (status: {unhealthy[0]['status']}, health: {unhealthy[0]['health']})")

            # Step 3c: Scan logs for root causes
            print(f"  → Analyzing logs for '{target}'...")
            res = await self.send_rpc("tools/call", {"name": "analyze_service_logs", "arguments": {"container_id_or_name": target}})
            analysis = json.loads(res["content"][0]["text"])
            print(f"    Anomalies found: {analysis['total_anomalies_detected']}")
            print(f"    Root Cause / Assessment: {analysis['health_assessment']}")
            print(f"    Recommended Remediation: {analysis['recommended_remediation']}")

            # Step 3d: Execute remediation
            if "flush_cache" in analysis["recommended_remediation"]:
                print(f"  → Executing automated remediation: 'flush_cache'...")
                res = await self.send_rpc("tools/call", {"name": "flush_cache", "arguments": {}})
                remediation = json.loads(res["content"][0]["text"])
                print(f"    ✅ Remediation complete: {remediation['result']}")

        # Step 3e: Demonstrate Human-in-the-Loop protection on critical tool
        print("\n[4] Testing Human-in-the-Loop Safety Protection (terminate_container)...")
        self.api_key = ADMIN_KEY  # Switch to admin credentials
        res = await self.send_rpc(
            "tools/call",
            {"name": "terminate_container", "arguments": {"container_id_or_name": "nexus-redis-cache"}},
        )
        data = json.loads(res["content"][0]["text"])
        if data.get("status") == "pending_approval":
            print(f"    🛡️ Action intercepted for Human Approval!")
            print(f"    Approval ID: {data['approval_id']}")
            print(f"    Reason: {data['reason']}")
            print(f"    Instruction: {data['instruction']}")


async def main():
    client = AutonomousAgentClient()
    try:
        await client.initialize()
        await client.discover_tools()
        await client.run_autonomous_diagnostic_and_remediation()
        print("\n🎉 Autonomous Agent demo executed successfully!")
    except Exception as exc:
        print(f"\n❌ Error during execution: {exc}")
        print("Note: Ensure the NexusOps server is running with 'python -m nexusops.main'")


if __name__ == "__main__":
    asyncio.run(main())
