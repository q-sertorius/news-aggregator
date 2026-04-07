from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
import os
import json


class PollingConfig(BaseModel):
    interval_minutes: int = 15
    max_pipeline_duration_minutes: int = 5


class FeedConfig(BaseModel):
    url: str
    category: str


class LLMConfig(BaseModel):
    model: str = "openrouter/free"
    base_url: str = "https://openrouter.ai/api/v1"
    max_tokens: int = 2000
    temperature: float = 0.1
    rate_limit_rpm: int = 15


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
    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
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
