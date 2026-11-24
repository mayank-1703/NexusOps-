"""FastAPI HTTP and Server-Sent Events (SSE) transport for MCP."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from nexusops.protocol.server import mcp_server
from nexusops.security.rbac import UserContext, authenticate_token

logger = logging.getLogger("nexusops.transport.http")
router = APIRouter(tags=["MCP Protocol"])


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> UserContext:
    """Resolve authentication context from headers."""
    token = authorization or x_api_key
    return authenticate_token(token)


@router.post("/mcp")
async def handle_mcp_post(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    """Primary JSON-RPC 2.0 endpoint for MCP communication."""
    try:
        body = await request.json()
    except Exception as exc:
        return Response(
            content=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(exc)}"},
                }
            ),
            media_type="application/json",
            status_code=400,
        )

    response_payload = await mcp_server.handle_message(body, user=user)

    if response_payload is None:
        # If the request was a notification, return 204 No Content
        return Response(status_code=204)

    return Response(
        content=json.dumps(response_payload),
        media_type="application/json",
    )


@router.get("/sse")
async def handle_mcp_sse(request: Request, user: UserContext = Depends(get_current_user)):
    """Server-Sent Events (SSE) endpoint conforming to the MCP transport specification."""

    async def event_generator():
        # First event advertises the message endpoint
        endpoint_event = {
            "event": "endpoint",
            "data": "/mcp",
        }
        yield f"event: {endpoint_event['event']}\ndata: {endpoint_event['data']}\n\n"

        # Keep connection open with periodic heartbeats / pings
        try:
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(15)
                yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
