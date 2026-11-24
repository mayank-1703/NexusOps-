"""Standard Input/Output (stdio) transport for MCP."""

import asyncio
import json
import sys
from typing import Optional
from nexusops.protocol.server import mcp_server
from nexusops.security.rbac import Role, UserContext


async def run_stdio_transport(user: Optional[UserContext] = None):
    """Run standard I/O loop for local MCP client integration (e.g. Claude Desktop)."""
    # By default, local stdio sessions are granted ADMIN privileges
    auth_user = user or UserContext(identity="local-stdio-agent", role=Role.ADMIN)

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break

        line_str = line.decode("utf-8").strip()
        if not line_str:
            continue

        try:
            raw_msg = json.loads(line_str)
        except Exception as exc:
            err_res = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(exc)}"},
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()
            continue

        response = await mcp_server.handle_message(raw_msg, user=auth_user)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
