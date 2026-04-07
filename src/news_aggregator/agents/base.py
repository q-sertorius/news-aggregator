# src/news_aggregator/agents/base.py

import openai
import json
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from ..config import AppConfig


class BaseAgent(ABC):
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = openai.AsyncOpenAI(
            api_key=config.openrouter_api_key, base_url=config.llm.base_url
        )

    @abstractmethod
    async def run(self, input_data: Any) -> Any:
        pass

    async def _call_llm(
        self, system_prompt: str, user_prompt: str, is_json: bool = True
    ) -> Any:
        """Call OpenRouter and handle retries/parsing."""

        for attempt in range(3):
            try:
                response = await self.client.chat.completions.create(
                    model=self.config.llm.model,
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
                    # Basic cleaning in case the model returns markdown blocks
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

            except Exception as e:
                print(f"LLM Call failed (attempt {attempt + 1}): {str(e)}")
                if attempt == 2:
                    raise e
                await asyncio.sleep(2**attempt)
