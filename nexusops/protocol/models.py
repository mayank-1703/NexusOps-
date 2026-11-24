"""JSON-RPC 2.0 & Model Context Protocol (MCP) data models.

Complies with the official Model Context Protocol specification:
https://spec.modelcontextprotocol.io
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ============================================================================
# Standard JSON-RPC 2.0 Specification
# ============================================================================

JSONRPC_VERSION = "2.0"


class JSONRPCErrorCode(int, Enum):
    """Standard and custom JSON-RPC error codes."""

    # Standard JSON-RPC 2.0 errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # NexusOps / MCP domain-specific errors
    UNAUTHORIZED = -32001
    APPROVAL_REQUIRED = -32002
    TOOL_EXECUTION_ERROR = -32003
    CIRCUIT_BREAKER_OPEN = -32004
    TIMEOUT_ERROR = -32005


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 Request or Notification."""

    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None
    id: Optional[Union[str, int]] = None

    @property
    def is_notification(self) -> bool:
        """True if the message is a notification (no ID to respond to)."""
        return self.id is None


class JSONRPCErrorObject(BaseModel):
    """JSON-RPC 2.0 Error details."""

    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 Success Response."""

    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    result: Any
    id: Optional[Union[str, int]] = None


class JSONRPCErrorResponse(BaseModel):
    """JSON-RPC 2.0 Error Response."""

    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    error: JSONRPCErrorObject
    id: Optional[Union[str, int]] = None


# ============================================================================
# Model Context Protocol (MCP) Data Models
# ============================================================================

MCP_PROTOCOL_VERSION = "2024-11-05"


class Implementation(BaseModel):
    """MCP Implementation information."""

    name: str
    version: str


class ClientCapabilities(BaseModel):
    """Client capabilities declared during initialization."""

    roots: Optional[Dict[str, Any]] = None
    sampling: Optional[Dict[str, Any]] = None
    experimental: Optional[Dict[str, Any]] = None


class ServerCapabilities(BaseModel):
    """Server capabilities advertised to clients."""

    tools: Optional[Dict[str, Any]] = Field(default_factory=lambda: {"listChanged": True})
    resources: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"subscribe": True, "listChanged": True}
    )
    prompts: Optional[Dict[str, Any]] = Field(default_factory=lambda: {"listChanged": True})
    logging: Optional[Dict[str, Any]] = Field(default_factory=dict)
    experimental: Optional[Dict[str, Any]] = None


class InitializeParams(BaseModel):
    """MCP 'initialize' request parameters."""

    protocolVersion: str
    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)
    clientInfo: Implementation


class InitializeResult(BaseModel):
    """MCP 'initialize' result payload."""

    protocolVersion: str = MCP_PROTOCOL_VERSION
    capabilities: ServerCapabilities = Field(default_factory=ServerCapabilities)
    serverInfo: Implementation


class ToolInputSchema(BaseModel):
    """JSON Schema defining tool arguments."""

    type: Literal["object"] = "object"
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: Optional[List[str]] = Field(default_factory=list)


class Tool(BaseModel):
    """Tool definition exposed by MCP server."""

    name: str
    description: str
    inputSchema: ToolInputSchema


class TextContent(BaseModel):
    """MCP text content block."""

    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """MCP image content block."""

    type: Literal["image"] = "image"
    data: str  # Base64 encoded
    mimeType: str


class ToolCallParams(BaseModel):
    """Parameters for 'tools/call'."""

    name: str
    arguments: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """Result returned for 'tools/call'."""

    content: List[Union[TextContent, ImageContent]]
    isError: bool = False
    metadata: Optional[Dict[str, Any]] = None


class Resource(BaseModel):
    """MCP Resource representation."""

    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


class ResourceContents(BaseModel):
    """Resource contents payload."""

    uri: str
    mimeType: Optional[str] = "text/plain"
    text: Optional[str] = None
    blob: Optional[str] = None


class PromptArgument(BaseModel):
    """MCP Prompt parameter definition."""

    name: str
    description: Optional[str] = None
    required: bool = False


class Prompt(BaseModel):
    """MCP Prompt template definition."""

    name: str
    description: Optional[str] = None
    arguments: Optional[List[PromptArgument]] = None


class PromptMessage(BaseModel):
    """Message returned by 'prompts/get'."""

    role: Literal["user", "assistant"]
    content: TextContent


class PromptGetResult(BaseModel):
    """Result returned by 'prompts/get'."""

    description: Optional[str] = None
    messages: List[PromptMessage]
