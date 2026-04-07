# src/news_aggregator/agents/base.py

import openai
import json
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from openai import RateLimitError
from ..config import AppConfig

logger = logging.getLogger(__name__)

# Global rate limiter - shared across all agent instances
_last_call_time = 0
_rate_lock = None
_MIN_CALL_INTERVAL = 12.0  # Minimum seconds between ANY LLM call

# Fallback models to try when openrouter/free is exhausted
_FALLBACK_MODELS = [
    "openrouter/free",
    "qwen/qwen3.6-plus:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "stepfun/step-3.5-flash:free",
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
        # Disable SDK's built-in retries — we handle rate limiting ourselves
        self.client = openai.AsyncOpenAI(
            api_key=config.openrouter_api_key,
            base_url=config.llm.base_url,
            max_retries=0,
        )

    @abstractmethod
    async def run(self, input_data: Any) -> Any:
        pass

    async def _call_llm(
        self, system_prompt: str, user_prompt: str, is_json: bool = True
    ) -> Any:
        """Call OpenRouter with global rate limiting, 429 retry, and model fallback."""
        global _last_call_time

        # Get the rate lock in the current event loop context
        rate_lock = _get_rate_lock()

        # Try each model in order until one succeeds
        for model_idx, model in enumerate(_FALLBACK_MODELS):
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
                        extra_headers={
                            "HTTP-Referer": "https://github.com/q-sertorius/news-aggregator",
                            "X-Title": "Agentic News Aggregator",
                        },
                    )

                    content = response.choices[0].message.content
                    if not content:
                        raise Exception("Empty response from LLM")

                    if is_json:
                        clean_content = content.strip()
                        if clean_content.startswith("```json"):
                            clean_content = (
                                clean_content.replace("```json", "", 1)
                                .replace("```", "", 1)
                                .strip()
                            )
                        result = json.loads(clean_content)
                        if result is None:
                            raise Exception("LLM returned 'null' as JSON")
                        return result

                    return content

                except RateLimitError:
                    if attempt == 0 and model_idx < len(_FALLBACK_MODELS) - 1:
                        logger.info(f"Model {model} rate-limited, trying next model...")
                        break  # Try next model
                    wait = 60
                    logger.warning(
                        f"Rate limited on {model}. Waiting {wait}s ({attempt + 1}/3)..."
                    )
                    await asyncio.sleep(wait)

                except Exception as e:
                    logger.warning(
                        f"LLM ({model}) failed (attempt {attempt + 1}): {str(e)}"
                    )
                    if attempt == 2:
                        if model_idx < len(_FALLBACK_MODELS) - 1:
                            break  # Try next model
                        raise e
                    await asyncio.sleep(2**attempt)
