"""Role-Based Access Control (RBAC) and Safety Classification for NexusOps."""

from enum import Enum
from typing import Optional, Set
from pydantic import BaseModel
from nexusops.config import settings


class Role(str, Enum):
    """User/Agent roles with hierarchical permissions."""

    READONLY = "readonly"
    OPERATOR = "operator"
    ADMIN = "admin"


class SafetyTier(str, Enum):
    """Safety classification for infrastructure operations."""

    SAFE = "safe"  # Read-only or idempotent non-destructive queries (e.g. get logs, list)
    MODERATE = "moderate"  # State modifying, but recoverable (e.g. restart container, flush cache)
    CRITICAL = "critical"  # High-impact, destructive, or irreversible (e.g. kill process, prune volumes)


class UserContext(BaseModel):
    """Identity and authorization context for the invoking agent or user."""

    identity: str
    role: Role
    token: Optional[str] = None


# Role hierarchy weights
ROLE_WEIGHTS = {
    Role.READONLY: 1,
    Role.OPERATOR: 2,
    Role.ADMIN: 3,
}

# Required role for safety tiers
TIER_MINIMUM_ROLE = {
    SafetyTier.SAFE: Role.READONLY,
    SafetyTier.MODERATE: Role.OPERATOR,
    SafetyTier.CRITICAL: Role.ADMIN,
}


def authenticate_token(token: Optional[str]) -> UserContext:
    """Validate API token and resolve UserContext with assigned Role."""
    if not token:
        # Default unauthenticated access is READONLY anonymous
        return UserContext(identity="anonymous", role=Role.READONLY, token=None)

    clean_token = token.replace("Bearer ", "").strip()

    if clean_token == settings.admin_api_key:
        return UserContext(identity="admin-agent", role=Role.ADMIN, token=clean_token)
    elif clean_token == settings.operator_api_key:
        return UserContext(identity="operator-agent", role=Role.OPERATOR, token=clean_token)
    elif clean_token == settings.readonly_api_key:
        return UserContext(identity="readonly-agent", role=Role.READONLY, token=clean_token)

    # Unknown token -> reject or fall back to readonly with anonymous identity
    return UserContext(identity="guest", role=Role.READONLY, token=clean_token)


def is_role_sufficient(user_role: Role, required_role: Role) -> bool:
    """Check if user_role satisfies required_role in the hierarchy."""
    return ROLE_WEIGHTS.get(user_role, 0) >= ROLE_WEIGHTS.get(required_role, 0)


def validate_access(user: UserContext, required_role: Role, safety_tier: SafetyTier) -> bool:
    """Validate if user context satisfies both role requirement and safety tier requirement."""
    min_role_for_tier = TIER_MINIMUM_ROLE[safety_tier]
    target_required_role = (
        required_role
        if ROLE_WEIGHTS[required_role] > ROLE_WEIGHTS[min_role_for_tier]
        else min_role_for_tier
    )
    return is_role_sufficient(user.role, target_required_role)
