"""NexusOps CLI and service entry point."""

import argparse
import asyncio
import logging
import sys
import uvicorn

from nexusops.config import settings
from nexusops.protocol.transport_stdio import run_stdio_transport
from nexusops.tools import register_all_tools, tool_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nexusops")


def main():
    """CLI parser and main dispatcher."""
    parser = argparse.ArgumentParser(
        description="NexusOps: Autonomous AI Infrastructure Control Plane via Model Context Protocol (MCP)"
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run in standard I/O mode for Claude Desktop / Cursor integration",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=settings.host,
        help=f"Bind host for HTTP/SSE server (default: {settings.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help=f"Bind port for HTTP/SSE server (default: {settings.port})",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Display all discoverable MCP infrastructure tools and exit",
    )

    args = parser.parse_args()

    # Pre-register tools
    register_all_tools()

    if args.list_tools:
        tools = tool_registry.get_tool_metadata()
        print(f"\nDiscovered {len(tools)} MCP Infrastructure Tools:\n" + "=" * 60)
        for name, meta in tools.items():
            print(f"• {name} [{meta['safety_tier'].upper()}] - Required Role: {meta['required_role']}")
            print(f"  {meta['description']}")
            print(f"  Requires Approval: {meta['requires_approval']}")
            print("-" * 60)
        sys.exit(0)

    if args.stdio:
        # Run stdio transport
        try:
            asyncio.run(run_stdio_transport())
        except (KeyboardInterrupt, BrokenPipeError):
            pass
    else:
        # Run HTTP / SSE FastAPI Control Plane
        logger.info("Starting NexusOps Control Plane on http://%s:%d", args.host, args.port)
        logger.info("MCP JSON-RPC 2.0 Endpoint: http://%s:%d/mcp", args.host, args.port)
        logger.info("MCP SSE Stream Endpoint:  http://%s:%d/sse", args.host, args.port)
        uvicorn.run(
            "nexusops.web.app:app",
            host=args.host,
            port=args.port,
            reload=False,
            log_level="info",
        )


if __name__ == "__main__":
    main()
