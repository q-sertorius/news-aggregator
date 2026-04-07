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
    max_articles_per_run: int = 5

    @classmethod
    def load(cls, config_path: str = "config.yaml"):
        """Load configuration from YAML and environment variables."""
        with open(config_path, "r") as f:
            yaml_config = yaml.safe_load(f)
        return cls(**yaml_config)
