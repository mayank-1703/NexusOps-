"""Custom Model Context Protocol (MCP) server implementation using JSON-RPC 2.0."""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from pydantic import ValidationError

from nexusops.config import settings
from nexusops.protocol.models import (
    JSONRPC_VERSION,
    JSONRPCErrorCode,
    JSONRPCErrorObject,
    JSONRPCErrorResponse,
    JSONRPCRequest,
    JSONRPCResponse,
    InitializeParams,
    InitializeResult,
    Implementation,
    Prompt,
    PromptArgument,
    PromptGetResult,
    PromptMessage,
    Resource,
    ResourceContents,
    ServerCapabilities,
    TextContent,
    ToolCallParams,
)
from nexusops.security.audit import audit_logger
from nexusops.security.rbac import Role, UserContext
from nexusops.tools.registry import tool_registry

logger = logging.getLogger("nexusops.mcp")


class MCPServer:
    """Core Model Context Protocol (MCP) Server.

    Implements capability negotiation, dynamic discovery, resource reading,
    prompt templating, and structured tool execution over JSON-RPC 2.0.
    """

    def __init__(self, name: Optional[str] = None, version: Optional[str] = None):
        self.name = name or settings.server_name
        self.version = version or settings.server_version
        self.initialized = False
        self.client_capabilities: Optional[Dict[str, Any]] = None

    def _build_error_response(
        self,
        request_id: Optional[Union[str, int]],
        code: JSONRPCErrorCode,
        message: str,
        data: Optional[Any] = None,
    ) -> JSONRPCErrorResponse:
        """Create a standard JSON-RPC 2.0 error response."""
        return JSONRPCErrorResponse(
            jsonrpc=JSONRPC_VERSION,
            id=request_id,
            error=JSONRPCErrorObject(code=code.value, message=message, data=data),
        )

    def _build_success_response(
        self, request_id: Optional[Union[str, int]], result: Any
    ) -> JSONRPCResponse:
        """Create a standard JSON-RPC 2.0 success response."""
        return JSONRPCResponse(
            jsonrpc=JSONRPC_VERSION,
            id=request_id,
            result=result,
        )

    async def handle_message(
        self,
        message: Union[Dict[str, Any], List[Dict[str, Any]]],
        user: Optional[UserContext] = None,
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """Process incoming JSON-RPC 2.0 request, batch of requests, or notifications."""
        # Handle batch requests
        if isinstance(message, list):
            responses = []
            for item in message:
                res = await self._handle_single_request(item, user)
                if res is not None:
                    responses.append(res.model_dump(exclude_none=True))
            return responses if responses else None

        # Handle single request
        res = await self._handle_single_request(message, user)
        return res.model_dump(exclude_none=True) if res is not None else None

    async def _handle_single_request(
        self,
        raw_msg: Dict[str, Any],
        user: Optional[UserContext] = None,
    ) -> Optional[Union[JSONRPCResponse, JSONRPCErrorResponse]]:
        """Dispatch a single parsed JSON-RPC request to the corresponding handler."""
        user_context = user or UserContext(identity="anonymous", role=Role.READONLY)

        # 1. Parse JSON-RPC envelope
        try:
            req = JSONRPCRequest.model_validate(raw_msg)
        except ValidationError as err:
            req_id = raw_msg.get("id") if isinstance(raw_msg, dict) else None
            return self._build_error_response(
                req_id,
                JSONRPCErrorCode.INVALID_REQUEST,
                "Invalid JSON-RPC 2.0 request structure",
                data=err.errors(),
            )

        # 2. Dispatch MCP Methods
        try:
            if req.method == "initialize":
                res_data = await self._handle_initialize(req.params)
            elif req.method == "notifications/initialized":
                self.initialized = True
                return None  # Notifications do not return a response
            elif req.method == "ping":
                res_data = {}
            elif req.method == "tools/list":
                res_data = await self._handle_tools_list(user_context)
            elif req.method == "tools/call":
                res_data = await self._handle_tools_call(req.params, user_context)
            elif req.method == "resources/list":
                res_data = await self._handle_resources_list()
            elif req.method == "resources/read":
                res_data = await self._handle_resources_read(req.params)
            elif req.method == "prompts/list":
                res_data = await self._handle_prompts_list()
            elif req.method == "prompts/get":
                res_data = await self._handle_prompts_get(req.params)
            else:
                return self._build_error_response(
                    req.id,
                    JSONRPCErrorCode.METHOD_NOT_FOUND,
                    f"Method '{req.method}' not supported by MCP server.",
                )

            # Notifications return None if no ID
            if req.is_notification:
                return None

            return self._build_success_response(req.id, res_data)

        except Exception as exc:
            logger.exception("Unexpected error processing MCP request: %s", exc)
            if req.is_notification:
                return None
            return self._build_error_response(
                req.id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                f"Internal server error: {str(exc)}",
            )

    # ------------------------------------------------------------------------
    # Protocol Method Implementations
    # ------------------------------------------------------------------------

    async def _handle_initialize(self, params: Any) -> Dict[str, Any]:
        """Capability negotiation during handshake."""
        init_params = InitializeParams.model_validate(params or {})
        self.client_capabilities = init_params.capabilities.model_dump()
        self.initialized = True

        result = InitializeResult(
            protocolVersion="2024-11-05",
            capabilities=ServerCapabilities(
                tools={"listChanged": True},
                resources={"subscribe": False, "listChanged": True},
                prompts={"listChanged": True},
                logging={},
            ),
            serverInfo=Implementation(
                name=self.name,
                version=self.version,
            ),
        )
        return result.model_dump()

    async def _handle_tools_list(self, user: UserContext) -> Dict[str, Any]:
        """Dynamic tool discovery returning registered tools and schemas."""
        tools = tool_registry.list_tools(user)
        return {"tools": [t.model_dump() for t in tools]}

    async def _handle_tools_call(self, params: Any, user: UserContext) -> Dict[str, Any]:
        """Structured tool invocation with arguments and RBAC checks."""
        if not params:
            raise ValueError("Missing parameters for 'tools/call'.")

        call_params = ToolCallParams.model_validate(params)
        approval_id = call_params.arguments.get("approval_id")

        result = await tool_registry.execute(
            name=call_params.name,
            arguments=call_params.arguments or {},
            user=user,
            approval_id=approval_id,
        )
        return result.model_dump(exclude_none=True)

    async def _handle_resources_list(self) -> Dict[str, Any]:
        """List exposed infrastructure resources."""
        resources = [
            Resource(
                uri="nexusops://system/metrics",
                name="Host System Metrics",
                description="Live CPU, Memory, and Disk metrics of the host system.",
                mimeType="application/json",
            ),
            Resource(
                uri="nexusops://containers/summary",
                name="Containers Summary",
                description="Live snapshot of all managed microservice containers and their health.",
                mimeType="application/json",
            ),
            Resource(
                uri="nexusops://audit/latest",
                name="Recent Audit Logs",
                description="Last 20 operational actions and security audit entries.",
                mimeType="application/json",
            ),
        ]
        return {"resources": [r.model_dump() for r in resources]}

    async def _handle_resources_read(self, params: Any) -> Dict[str, Any]:
        """Read resource content by URI."""
        uri = (params or {}).get("uri")
        if not uri:
            raise ValueError("Parameter 'uri' is required for 'resources/read'.")

        if uri == "nexusops://system/metrics":
            from nexusops.tools.system_tools import get_system_metrics

            metrics = get_system_metrics()
            return {
                "contents": [
                    ResourceContents(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps(metrics, indent=2),
                    ).model_dump()
                ]
            }
        elif uri == "nexusops://containers/summary":
            from nexusops.tools.container_tools import list_containers

            containers = list_containers()
            return {
                "contents": [
                    ResourceContents(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps(containers, indent=2),
                    ).model_dump()
                ]
            }
        elif uri == "nexusops://audit/latest":
            entries = audit_logger.query(limit=20)
            return {
                "contents": [
                    ResourceContents(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps([e.model_dump() for e in entries], indent=2),
                    ).model_dump()
                ]
            }
        else:
            raise ValueError(f"Resource URI not found: {uri}")

    async def _handle_prompts_list(self) -> Dict[str, Any]:
        """List pre-defined agent prompts and runbooks."""
        prompts = [
            Prompt(
                name="diagnose-incident",
                description="Analyze current infrastructure health, logs, and metrics to identify root cause.",
                arguments=[
                    PromptArgument(
                        name="service_name",
                        description="Optional service name to narrow diagnosis",
                        required=False,
                    )
                ],
            ),
            Prompt(
                name="remediate-service",
                description="Multi-step guided remediation plan for degraded microservices.",
                arguments=[
                    PromptArgument(
                        name="service_name",
                        description="Service to remediate",
                        required=True,
                    ),
                    PromptArgument(
                        name="strategy",
                        description="Remediation strategy: 'restart', 'flush_cache', or 'scale'",
                        required=False,
                    ),
                ],
            ),
        ]
        return {"prompts": [p.model_dump() for p in prompts]}

    async def _handle_prompts_get(self, params: Any) -> Dict[str, Any]:
        """Generate prompt message templates for an AI agent."""
        name = (params or {}).get("name")
        args = (params or {}).get("arguments", {})

        if name == "diagnose-incident":
            target = args.get("service_name", "all services")
            prompt_text = (
                f"You are the NexusOps Infrastructure Copilot.\n"
                f"Conduct a thorough diagnostic review of {target}.\n"
                f"1. Call 'list_containers' and 'get_system_metrics' to assess overall health.\n"
                f"2. For any degraded or failing container, call 'analyze_service_logs' to identify root causes.\n"
                f"3. Formulate a remediation recommendation before requesting tool execution."
            )
            return PromptGetResult(
                description="Automated diagnostic runbook",
                messages=[PromptMessage(role="user", content=TextContent(text=prompt_text))],
            ).model_dump()

        elif name == "remediate-service":
            svc = args.get("service_name", "unknown")
            strat = args.get("strategy", "restart")
            prompt_text = (
                f"Initiate remediation for service '{svc}' using strategy '{strat}'.\n"
                f"1. Check service health with 'check_service_health'.\n"
                f"2. Execute remediation tool ('{strat}_service' or equivalent).\n"
                f"3. Note that CRITICAL actions will pause for Human-in-the-Loop approval.\n"
                f"4. Verify post-remediation health."
            )
            return PromptGetResult(
                description=f"Remediation runbook for {svc}",
                messages=[PromptMessage(role="user", content=TextContent(text=prompt_text))],
            ).model_dump()

        else:
            raise ValueError(f"Prompt '{name}' not found.")


# Global default MCP server instance
mcp_server = MCPServer()
