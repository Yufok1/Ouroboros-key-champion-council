from __future__ import annotations

from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    app_env: str = Field(default="development")
    app_port: int = Field(default=7866)
    mcp_port: int = Field(default=8766)
    persistence_mode: str = Field(default="local")


class ProviderConfig(BaseModel):
    hf_token: str = Field(default="")
    vast_api_key: str = Field(default="")
    brave_api_key: str = Field(default="")
    serper_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")


class SelfDeployConfig(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    providers: ProviderConfig = Field(default_factory=ProviderConfig)
