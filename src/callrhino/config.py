from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_OPENAI_BUDGET_USD = Decimal("1.50")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sarvam_api_key: str | None = Field(default=None, alias="SARVAM_API_KEY")
    sarvam_chat_model: str = Field(default="sarvam-105b", alias="SARVAM_CHAT_MODEL")
    sarvam_max_output_tokens: int = Field(
        default=4096,
        ge=512,
        le=4096,
        alias="SARVAM_MAX_OUTPUT_TOKENS",
    )
    sarvam_base_url: str = Field(
        default="https://api.sarvam.ai",
        alias="SARVAM_BASE_URL",
    )
    sarvam_timeout_seconds: float = Field(default=90, alias="SARVAM_TIMEOUT_SECONDS")
    sarvam_batch_poll_seconds: float = Field(
        default=5,
        gt=0,
        alias="SARVAM_BATCH_POLL_SECONDS",
    )
    sarvam_batch_timeout_seconds: float = Field(
        default=1800,
        gt=0,
        alias="SARVAM_BATCH_TIMEOUT_SECONDS",
    )
    candidate_gating_enabled: bool = Field(
        default=False,
        alias="CALLRHINO_CANDIDATE_GATING_ENABLED",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.4-nano", alias="OPENAI_MODEL")
    openai_fallback_enabled: bool = Field(
        default=False,
        alias="OPENAI_FALLBACK_ENABLED",
    )
    openai_soft_budget_usd: Decimal = Field(
        default=Decimal("1.25"),
        ge=0,
        alias="OPENAI_SOFT_BUDGET_USD",
    )
    openai_hard_budget_usd: Decimal = Field(
        default=MAX_OPENAI_BUDGET_USD,
        ge=0,
        le=MAX_OPENAI_BUDGET_USD,
        alias="OPENAI_HARD_BUDGET_USD",
    )

    storage_backend: Literal["sqlite", "supabase"] = Field(
        default="sqlite",
        alias="CALLRHINO_STORAGE_BACKEND",
    )
    db_path: Path = Field(default=Path("data/callrhino.db"), alias="CALLRHINO_DB_PATH")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_publishable_key: str | None = Field(
        default=None,
        alias="SUPABASE_PUBLISHABLE_KEY",
    )

    @model_validator(mode="after")
    def validate_openai_budget(self) -> "Settings":
        if self.openai_soft_budget_usd > self.openai_hard_budget_usd:
            raise ValueError("OPENAI_SOFT_BUDGET_USD cannot exceed the hard budget.")
        return self

    @property
    def sarvam_chat_url(self) -> str:
        return f"{self.sarvam_base_url.rstrip('/')}/v1/chat/completions"

    @property
    def has_sarvam_credentials(self) -> bool:
        return bool(self.sarvam_api_key)

    @property
    def has_openai_credentials(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def openai_fallback_active(self) -> bool:
        return self.has_openai_credentials and self.openai_fallback_enabled

    @property
    def has_supabase_credentials(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    def ensure_storage_directory(self) -> None:
        if self.storage_backend == "sqlite":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
