# src/news_aggregator/config.py

from typing import List, Dict, Optional, Any, Union
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    ValidationError,
    FieldValidationInfo,
)  # Added FieldValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
import os
import json
from enum import Enum  # Added Enum


class PollingConfig(BaseModel):
    interval_minutes: int = 15
    max_pipeline_duration_minutes: int = 5


class FeedConfig(BaseModel):
    url: str
    category: str


# New Enum for LLM Provider
class LLMProvider(str, Enum):
    OPENROUTER = "OPENROUTER"
    OLLAMA = "OLLAMA"


class LLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.OPENROUTER  # New provider field
    model: str = "google/gemini-pro"  # Default to a reliable paid model
    base_url: Optional[str] = (
        None  # Default to None, will be set by BaseAgent based on provider
    )
    ollama_base_url: Optional[str] = (
        "http://localhost:11434/v1"  # Default Ollama URL, optional
    )
    max_tokens: int = 2000
    temperature: float = 0.1
    rate_limit_rpm: int = 15

    @field_validator("ollama_base_url", mode="after")
    @classmethod
    def validate_ollama_url(cls, v: Optional[str], info: FieldValidationInfo) -> str:
        if info.data.get("provider") == LLMProvider.OLLAMA and not v:
            raise ValueError("ollama_base_url must be provided when provider is OLLAMA")
        return v


class ImpactConfig(BaseModel):
    weights: Dict[str, float]
    thresholds: Dict[str, float]


class RetentionConfig(BaseModel):
    db_retention_days: int = 30
    max_articles_per_subject: int = 50


class TelegramConfig(BaseModel):
    report_format: str = "markdownv2"
    enable_inline_buttons: bool = True
    notification_threshold: str = "MEDIUM"
    max_message_length: int = 4000


class WatchlistTopic(BaseModel):
    name: str
    keywords: List[str]
    priority: int = 1


class WatchlistConfig(BaseModel):
    topics: List[WatchlistTopic]


class AppConfig(BaseSettings):
    openrouter_api_key: Optional[str] = Field(
        None, validation_alias="OPENROUTER_API_KEY"
    )  # Made optional
    telegram_bot_token: str = Field(..., validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_ids: List[int] = Field(..., validation_alias="TELEGRAM_CHAT_IDS")

    @field_validator("telegram_chat_ids", mode="before")
    @classmethod
    def parse_chat_ids(cls, v: Any) -> List[int]:
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [int(x) for x in parsed]
                if isinstance(parsed, int):
                    return [parsed]
            except (json.JSONDecodeError, ValueError):
                return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return v

    @field_validator("openrouter_api_key", mode="after")
    @classmethod
    def validate_openrouter_api_key(
        cls, v: Optional[str], info: FieldValidationInfo
    ) -> Optional[str]:
        llm_config_data = info.data.get("llm")
        if (
            llm_config_data
            and llm_config_data.get("provider") == LLMProvider.OPENROUTER
            and not v
        ):
            raise ValueError(
                "OPENROUTER_API_KEY must be provided when LLM provider is OPENROUTER"
            )
        return v

    polling: PollingConfig
    feeds: List[FeedConfig]
    llm: LLMConfig
    impact: ImpactConfig
    retention: RetentionConfig
    telegram: TelegramConfig
    watchlist: WatchlistConfig

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @classmethod
    def load(cls, config_path: str = "config.yaml"):
        """Load configuration from YAML and environment variables."""
        with open(config_path, "r") as f:
            yaml_config = yaml.safe_load(f)
        return cls(**yaml_config)
