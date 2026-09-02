import os
from pydantic import BaseModel, Field


class SidecarSettings(BaseModel):
    """Configuration settings for the VigilantAI Sidecar Proxy."""

    sidecar_host: str = Field(
        default_factory=lambda: os.getenv("SIDECAR_HOST", "0.0.0.0")
    )
    sidecar_port: int = Field(
        default_factory=lambda: int(os.getenv("SIDECAR_PORT", "8000"))
    )
    target_llm_url: str = Field(
        default_factory=lambda: os.getenv("TARGET_LLM_URL", "http://localhost:11434").rstrip("/")
    )
    timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("SIDECAR_TIMEOUT", "120.0"))
    )
    enable_debug_logging: bool = Field(
        default_factory=lambda: os.getenv("SIDECAR_DEBUG", "false").lower() == "true"
    )


settings = SidecarSettings()
