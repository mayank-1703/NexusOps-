"""Configuration settings for NexusOps."""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """NexusOps central configuration."""

    model_config = SettingsConfigDict(
        env_prefix="NEXUSOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    env: str = "development"
    server_name: str = "NexusOps-ControlPlane"
    server_version: str = "0.1.0"

    # Security & API Keys
    admin_api_key: str = "nexus-admin-secret-key-12345"
    operator_api_key: str = "nexus-operator-secret-key-67890"
    readonly_api_key: str = "nexus-readonly-secret-key-abcde"

    # Human-in-the-Loop configuration
    approval_timeout_seconds: int = 300
    auto_approve_safe_actions: bool = True

    # Multi-server Orchestration
    upstream_mcp_servers: List[str] = Field(default_factory=list)
    orchestrator_concurrency_limit: int = 10
    tool_timeout_seconds: float = 30.0

    # Simulation / Mock mode (active when real docker daemon is absent)
    force_mock_containers: bool = False


settings = Settings()
