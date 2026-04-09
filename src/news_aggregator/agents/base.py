# src/news_aggregator/agents/base.py

import openai
import json
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from openai import (
    RateLimitError,
    OpenAIError,
)
from ..config import AppConfig, LLMProvider  # Import LLMProvider

logger = logging.getLogger(__name__)

# Global rate limiter - shared across all agent instances
_last_call_time = 0
_rate_lock = None
_MIN_CALL_INTERVAL = 15.0

# OpenRouter specific fallback models (only used when provider is OPENROUTER)
_OPENROUTER_FALLBACK_MODELS = [
    "google/gemini-pro",
    "mistralai/mistral-large",
    "openai/gpt-4o",
    "google/gemini-flash-1.5",
    "meta-llama/llama-3.1-400b-instruct",
    "qwen/qwen3.6-plus",
    "nvidia/nemotron-3-super-120b-a12b",
    "qwen/qwen3-next-80b-a3b-instruct",
    "stepfun/step-3.5-flash",
]


def _get_rate_lock():
    """Get or create the rate lock in the current event loop context."""
    global _rate_lock
    if _rate_lock is None:
        _rate_lock = asyncio.Lock()
    return _rate_lock


class BaseAgent(ABC):
    def __init__(self, config: AppConfig):
        self.config = config
        self.client: openai.AsyncOpenAI  # Declare client type for clarity

        if self.config.llm.provider == LLMProvider.OPENROUTER:
            if not self.config.openrouter_api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY must be set for OPENROUTER provider."
                )
            client_base_url = self.config.llm.base_url
            client_api_key = self.config.openrouter_api_key
        elif self.config.llm.provider == LLMProvider.OLLAMA:
            if not self.config.llm.ollama_base_url:
                raise ValueError("ollama_base_url must be set for OLLAMA provider.")
            client_base_url = self.config.llm.ollama_base_url
            client_api_key = "ollama"
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config.llm.provider}")

        self.client = openai.AsyncOpenAI(
            api_key=client_api_key,
            base_url=client_base_url,
            max_retries=0,
        )

        self.current_model = self.config.llm.model
        self.fallback_models = []
        if self.config.llm.provider == LLMProvider.OPENROUTER:
            self.fallback_models = [self.current_model] + [
                m for m in _OPENROUTER_FALLBACK_MODELS if m != self.current_model
            ]
        elif self.config.llm.provider == LLMProvider.OLLAMA:
            self.fallback_models = [self.current_model]

    @abstractmethod
    async def run(self, input_data: Any) -> Any:
        pass

    async def _call_llm(
        self, system_prompt: str, user_prompt: str, is_json: bool = True
    ) -> Any:
        """Call LLM with global rate limiting, retry, and model fallback (for OpenRouter)."""
        global _last_call_time

        rate_lock = _get_rate_lock()

        models_to_try = []
        if self.config.llm.provider == LLMProvider.OPENROUTER:
            models_to_try = [self.current_model] + [
                m for m in self.fallback_models if m != self.current_model
            ]
        elif self.config.llm.provider == LLMProvider.OLLAMA:
            models_to_try = [self.current_model]
        else:
            raise ValueError(
                f"Unsupported LLM provider for _call_llm: {self.config.llm.provider}"
            )

        extra_headers = {}  # Determine extra headers dynamically
        if self.config.llm.provider == LLMProvider.OPENROUTER:
            extra_headers = {
                "HTTP-Referer": "https://github.com/q-sertorius/news-aggregator",
                "X-Title": "Agentic News Aggregator",
            }

        for model_idx, model in enumerate(models_to_try):
            for attempt in range(3):
                async with rate_lock:
                    elapsed = time.time() - _last_call_time
                    if elapsed < _MIN_CALL_INTERVAL:
                        wait = _MIN_CALL_INTERVAL - elapsed
                        await asyncio.sleep(wait)
                    _last_call_time = time.time()

                try:
                    response = await self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=self.config.llm.max_tokens,
                        temperature=self.config.llm.temperature,
                        response_format={"type": "json_object"} if is_json else None,
                        extra_headers=extra_headers,  # Use dynamically determined headers
                    )

                    if not response.choices:
                        raise Exception("LLM response.choices is empty.")

                    message_content = response.choices[0].message.content
                    if not message_content:
                        raise Exception("Empty content in LLM response message.")

                    if is_json:
                        clean_content = message_content.strip()
                        if clean_content.startswith("```json"):
                            clean_content = (
                                clean_content.replace("```json", "", 1)
                                .replace("```", "", 1)
                                .strip()
                            )

                        try:
                            result = json.loads(clean_content)
                        except json.JSONDecodeError as jde:
                            raise Exception(
                                f"Failed to decode JSON from LLM: {jde}. Content: {clean_content[:200]}"
                            )

                        if not isinstance(result, dict):
                            raise Exception(
                                f"LLM returned non-dict JSON: {type(result).__name__}. Content: {clean_content[:200]}"
                            )
                        if result is None:
                            raise Exception("LLM returned 'null' as JSON")
                        return result

                    return message_content

                except RateLimitError:
                    if (
                        self.config.llm.provider == LLMProvider.OPENROUTER
                        and attempt < 2
                        and model_idx < len(models_to_try) - 1
                    ):
                        logger.info(
                            f"OpenRouter model {model} rate-limited, trying next model or retrying this one..."
                        )
                        break
                    elif attempt < 2:
                        wait = 60
                        logger.warning(
                            f"Rate limited on {model}. Waiting {wait}s (attempt {attempt + 1}/3)..."
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise Exception(f"Rate limited on {model} after 3 attempts.")

                except OpenAIError as e:
                    logger.warning(
                        f"LLM ({model}) OpenAI error (attempt {attempt + 1}): {str(e)}"
                    )
                    if (
                        self.config.llm.provider == LLMProvider.OPENROUTER
                        and attempt < 2
                        and model_idx < len(models_to_try) - 1
                    ):
                        logger.info(
                            f"OpenAIError on OpenRouter model {model}, trying next model or retrying this one..."
                        )
                        break
                    elif attempt < 2:
                        await asyncio.sleep(2**attempt)
                    else:
                        raise e

                except Exception as e:
                    logger.warning(
                        f"LLM ({model}) unexpected error (attempt {attempt + 1}): {str(e)}"
                    )
                    if attempt == 2:
                        if (
                            self.config.llm.provider == LLMProvider.OPENROUTER
                            and model_idx < len(models_to_try) - 1
                        ):
                            break
                        raise e
                    await asyncio.sleep(2**attempt)
            else:
                if (
                    self.config.llm.provider == LLMProvider.OPENROUTER
                    and model_idx < len(models_to_try) - 1
                ):
                    continue
                else:
                    raise Exception("All LLM models failed after multiple retries.")
        raise Exception("Unhandled exit from _call_llm loop.")
