"""Unit tests for Role-Based Access Control (RBAC)."""

import pytest
from nexusops.config import settings
from nexusops.security.rbac import (
    Role,
    SafetyTier,
    UserContext,
    authenticate_token,
    validate_access,
)
from nexusops.tools.registry import tool_registry


def test_token_authentication():
    """Test resolving UserContext from tokens."""
    admin_ctx = authenticate_token(settings.admin_api_key)
    assert admin_ctx.role == Role.ADMIN

    operator_ctx = authenticate_token(f"Bearer {settings.operator_api_key}")
    assert operator_ctx.role == Role.OPERATOR

    readonly_ctx = authenticate_token(settings.readonly_api_key)
    assert readonly_ctx.role == Role.READONLY

    anon_ctx = authenticate_token(None)
    assert anon_ctx.role == Role.READONLY


def test_role_hierarchy_permissions():
    """Test hierarchy rules."""
    viewer = UserContext(identity="v", role=Role.READONLY)
    operator = UserContext(identity="o", role=Role.OPERATOR)
    admin = UserContext(identity="a", role=Role.ADMIN)

    # SAFE tier
    assert validate_access(viewer, Role.READONLY, SafetyTier.SAFE) is True
    assert validate_access(operator, Role.READONLY, SafetyTier.SAFE) is True
    assert validate_access(admin, Role.READONLY, SafetyTier.SAFE) is True

    # MODERATE tier
    assert validate_access(viewer, Role.OPERATOR, SafetyTier.MODERATE) is False
    assert validate_access(operator, Role.OPERATOR, SafetyTier.MODERATE) is True
    assert validate_access(admin, Role.OPERATOR, SafetyTier.MODERATE) is True

    # CRITICAL tier
    assert validate_access(viewer, Role.ADMIN, SafetyTier.CRITICAL) is False
    assert validate_access(operator, Role.ADMIN, SafetyTier.CRITICAL) is False
    assert validate_access(admin, Role.ADMIN, SafetyTier.CRITICAL) is True


@pytest.mark.asyncio
async def test_rbac_tool_execution_enforcement():
    """Test runtime rejection when invoking unauthorized tools."""
    viewer = UserContext(identity="viewer-agent", role=Role.READONLY)

    # Viewer attempting to restart service -> unauthorized
    res = await tool_registry.execute("restart_service", {"service_name": "nexus-redis-cache"}, user=viewer)
    assert res.isError is True
    assert "Permission denied" in res.content[0].text
