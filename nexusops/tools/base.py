"""Base tool definition, decorator, and JSON Schema generation for MCP."""

import asyncio
from dataclasses import dataclass, field
import functools
import inspect
import json
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints
from pydantic import TypeAdapter
from nexusops.protocol.models import (
    TextContent,
    Tool,
    ToolCallResult,
    ToolInputSchema,
)
from nexusops.security.rbac import Role, SafetyTier, UserContext


@dataclass
class ToolMetadata:
    """Metadata describing an infrastructure tool."""

    name: str
    description: str
    handler: Callable
    required_role: Role = Role.READONLY
    safety_tier: SafetyTier = SafetyTier.SAFE
    requires_approval: bool = False
    timeout_seconds: float = 30.0
    schema: Dict[str, Any] = field(default_factory=dict)


def python_type_to_json_type(py_type: Any) -> Dict[str, Any]:
    """Map python types to JSON schema types."""
    if py_type is str:
        return {"type": "string"}
    elif py_type is int:
        return {"type": "integer"}
    elif py_type is float:
        return {"type": "number"}
    elif py_type is bool:
        return {"type": "boolean"}
    elif py_type is list or getattr(py_type, "__origin__", None) is list:
        return {"type": "array"}
    elif py_type is dict or getattr(py_type, "__origin__", None) is dict:
        return {"type": "object"}
    else:
        return {"type": "string"}


def extract_json_schema(func: Callable) -> ToolInputSchema:
    """Extract standard JSON Schema from Python function signature & type hints."""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)
    properties: Dict[str, Any] = {}
    required: List[str] = []

    # Parameters to ignore (injected by runtime)
    injected_params = {"user_context", "user", "context"}

    for param_name, param in sig.parameters.items():
        if param_name in injected_params:
            continue

        param_type = type_hints.get(param_name, str)
        schema_prop = python_type_to_json_type(param_type)

        # Inspect docstrings if possible for param description
        schema_prop["description"] = f"Parameter '{param_name}'"

        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            schema_prop["default"] = param.default

        properties[param_name] = schema_prop

    return ToolInputSchema(
        type="object",
        properties=properties,
        required=required if required else [],
    )


def mcp_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    required_role: Role = Role.READONLY,
    safety_tier: SafetyTier = SafetyTier.SAFE,
    requires_approval: bool = False,
    timeout_seconds: float = 30.0,
):
    """Decorator to declare an MCP-compliant infrastructure tool."""

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_desc = (description or func.__doc__ or "No description provided.").strip()

        schema = extract_json_schema(func)

        metadata = ToolMetadata(
            name=tool_name,
            description=tool_desc,
            handler=func,
            required_role=required_role,
            safety_tier=safety_tier,
            requires_approval=requires_approval or (safety_tier == SafetyTier.CRITICAL),
            timeout_seconds=timeout_seconds,
            schema=schema.model_dump(),
        )

        func.__mcp_tool__ = metadata  # type: ignore
        return func

    return decorator


def format_tool_result(result: Any, is_error: bool = False, metadata: Optional[Dict[str, Any]] = None) -> ToolCallResult:
    """Format any Python return value into a standard MCP ToolCallResult."""
    if isinstance(result, ToolCallResult):
        return result

    if isinstance(result, (dict, list)):
        text_payload = json.dumps(result, indent=2)
    else:
        text_payload = str(result)

    return ToolCallResult(
        content=[TextContent(type="text", text=text_payload)],
        isError=is_error,
        metadata=metadata,
    )
