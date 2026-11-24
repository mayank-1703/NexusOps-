"""Dynamic tool discovery registry and execution dispatcher for NexusOps."""

import asyncio
import inspect
import time
from typing import Any, Callable, Dict, List, Optional
from nexusops.protocol.models import (
    TextContent,
    Tool,
    ToolCallResult,
    ToolInputSchema,
)
from nexusops.security.approvals import (
    ApprovalStatus,
    approval_manager,
)
from nexusops.security.audit import audit_logger
from nexusops.security.rbac import (
    Role,
    SafetyTier,
    UserContext,
    validate_access,
)
from nexusops.tools.base import ToolMetadata, format_tool_result


class ToolRegistry:
    """Dynamic registry managing discovery, RBAC validation, and invocation of tools."""

    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}

    def register(self, tool_func_or_metadata: Any) -> ToolMetadata:
        """Register a tool into the catalog."""
        if hasattr(tool_func_or_metadata, "__mcp_tool__"):
            meta: ToolMetadata = tool_func_or_metadata.__mcp_tool__
        elif isinstance(tool_func_or_metadata, ToolMetadata):
            meta = tool_func_or_metadata
        else:
            raise ValueError("Object must be decorated with @mcp_tool or be an instance of ToolMetadata.")

        self._tools[meta.name] = meta
        return meta

    def get(self, name: str) -> Optional[ToolMetadata]:
        """Fetch tool metadata by name."""
        return self._tools.get(name)

    def list_tools(self, user: Optional[UserContext] = None) -> List[Tool]:
        """List all discoverable tools matching MCP spec.
        Optionally filters based on user authorization if configured."""
        mcp_tools = []
        for meta in self._tools.values():
            mcp_tools.append(
                Tool(
                    name=meta.name,
                    description=f"[{meta.safety_tier.value.upper()}] {meta.description} (Requires: {meta.required_role.value})",
                    inputSchema=ToolInputSchema(
                        type="object",
                        properties=meta.schema.get("properties", {}),
                        required=meta.schema.get("required", []),
                    ),
                )
            )
        return mcp_tools

    def get_tool_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Return enriched tool metadata for the control plane UI."""
        return {
            name: {
                "name": meta.name,
                "description": meta.description,
                "required_role": meta.required_role.value,
                "safety_tier": meta.safety_tier.value,
                "requires_approval": meta.requires_approval,
                "timeout_seconds": meta.timeout_seconds,
                "parameters": meta.schema.get("properties", {}),
                "required": meta.schema.get("required", []),
            }
            for name, meta in self._tools.items()
        }

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        user: UserContext,
        approval_id: Optional[str] = None,
    ) -> ToolCallResult:
        """Execute a tool with full RBAC, HITL approval check, timeout, and audit logging."""
        start_time = time.time()
        tool = self.get(name)

        # Allow approval_id to be passed inside arguments dict or as explicit kwarg
        effective_approval_id = approval_id or arguments.get("approval_id")

        if not tool:
            duration_ms = (time.time() - start_time) * 1000
            audit_logger.log(
                requester=user.identity,
                role=user.role.value,
                tool_name=name,
                arguments=arguments,
                status="FAILED",
                duration_ms=duration_ms,
                error_message=f"Tool '{name}' not found",
            )
            return format_tool_result(f"Error: Tool '{name}' not found in registry.", is_error=True)

        # 1. RBAC Validation
        if not validate_access(user, tool.required_role, tool.safety_tier):
            duration_ms = (time.time() - start_time) * 1000
            err_msg = (
                f"Permission denied: User '{user.identity}' with role '{user.role.value}' "
                f"cannot execute '{name}' (requires role '{tool.required_role.value}' and tier '{tool.safety_tier.value}')."
            )
            audit_logger.log(
                requester=user.identity,
                role=user.role.value,
                tool_name=name,
                arguments=arguments,
                status="UNAUTHORIZED",
                duration_ms=duration_ms,
                error_message=err_msg,
            )
            return format_tool_result(err_msg, is_error=True)

        # 2. Human-in-the-Loop Approval Check
        if tool.requires_approval:
            # Check if this invocation includes an existing approved request
            if effective_approval_id:
                app_req = approval_manager.get_request(effective_approval_id)
                if not app_req:
                    return format_tool_result(f"Error: Approval request '{effective_approval_id}' not found.", is_error=True)
                if app_req.status == ApprovalStatus.REJECTED:
                    return format_tool_result(
                        f"Execution aborted: Approval request '{effective_approval_id}' was REJECTED by human operator ({app_req.decision_by}): {app_req.decision_note}",
                        is_error=True,
                    )
                if app_req.status == ApprovalStatus.EXPIRED:
                    return format_tool_result(f"Execution aborted: Approval request '{effective_approval_id}' EXPIRED.", is_error=True)
                if app_req.status != ApprovalStatus.APPROVED:
                    return format_tool_result(
                        f"Execution blocked: Approval request '{effective_approval_id}' is still in status '{app_req.status.value}'.",
                        is_error=True,
                    )
                # Valid approval present! Proceed to execution
            else:
                # No approval provided yet -> Create pending approval request and return pause payload
                reason = f"High-risk action '{name}' (tier: {tool.safety_tier.value}) requires human sign-off."
                req = approval_manager.create_request(
                    tool_name=name,
                    arguments=arguments,
                    user=user,
                    safety_tier=tool.safety_tier,
                    reason=reason,
                    timeout_seconds=int(tool.timeout_seconds * 10),
                )
                duration_ms = (time.time() - start_time) * 1000
                audit_logger.log(
                    requester=user.identity,
                    role=user.role.value,
                    tool_name=name,
                    arguments=arguments,
                    status="PENDING_APPROVAL",
                    duration_ms=duration_ms,
                    approval_id=req.id,
                )
                pending_response = {
                    "status": "pending_approval",
                    "approval_id": req.id,
                    "tool": name,
                    "safety_tier": tool.safety_tier.value,
                    "reason": reason,
                    "expires_at": req.expires_at,
                    "instruction": f"Action paused. A human operator must review and approve approval_id '{req.id}' via the control plane before execution can proceed.",
                }
                return format_tool_result(pending_response, is_error=False, metadata={"requires_approval": True, "approval_id": req.id})

        # 3. Execution with Fault Isolation and Timeout
        clean_args = {k: v for k, v in arguments.items() if k != "approval_id"}
        try:
            # Check if function accepts user_context
            sig = inspect.signature(tool.handler)
            if "user_context" in sig.parameters:
                clean_args["user_context"] = user

            if inspect.iscoroutinefunction(tool.handler):
                result = await asyncio.wait_for(
                    tool.handler(**clean_args),
                    timeout=tool.timeout_seconds,
                )
            else:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool.handler(**clean_args)),
                    timeout=tool.timeout_seconds,
                )

            duration_ms = (time.time() - start_time) * 1000
            audit_logger.log(
                requester=user.identity,
                role=user.role.value,
                tool_name=name,
                arguments=arguments,
                status="SUCCESS",
                duration_ms=duration_ms,
                approval_id=effective_approval_id,
                result_summary=str(result)[:200],
            )

            if effective_approval_id:
                approval_manager.mark_executed(effective_approval_id, result)

            return format_tool_result(result, is_error=False)

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            err_msg = f"Tool execution timed out after {tool.timeout_seconds}s."
            audit_logger.log(
                requester=user.identity,
                role=user.role.value,
                tool_name=name,
                arguments=arguments,
                status="TIMEOUT",
                duration_ms=duration_ms,
                error_message=err_msg,
                approval_id=approval_id,
            )
            return format_tool_result(err_msg, is_error=True)

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            err_msg = f"Tool execution failed: {type(exc).__name__}: {str(exc)}"
            audit_logger.log(
                requester=user.identity,
                role=user.role.value,
                tool_name=name,
                arguments=arguments,
                status="FAILED",
                duration_ms=duration_ms,
                error_message=err_msg,
                approval_id=approval_id,
            )
            return format_tool_result(err_msg, is_error=True)


# Global tool registry
tool_registry = ToolRegistry()
