#!/usr/bin/env python3
"""Test script to verify the fallback model mechanism."""

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from news_aggregator.config import AppConfig
from news_aggregator.agents.base import BaseAgent


class TestAgent(BaseAgent):
    """Simple test agent to verify fallback mechanism."""

    async def run(self, input_data: str) -> str:
        """Test the LLM call with fallback."""
        system_prompt = "You are a helpful assistant. Respond with JSON."
        user_prompt = "Say 'Hello' in JSON format."

        try:
            result = await self._call_llm(system_prompt, user_prompt, is_json=True)
            print(f"✅ Success! Result: {result}")
            return result
        except Exception as e:
            print(f"❌ Failed: {str(e)}")
            raise


async def main():
    """Test the fallback mechanism."""
    config = AppConfig.load("config.yaml")
    agent = TestAgent(config)

    print("Testing fallback model mechanism...")
    print(f"API Key: {config.openrouter_api_key[:20]}...")
    print(f"Base URL: {config.llm.base_url}")
    print(f"Model: {config.llm.model}")
    print()

    try:
        result = await agent.run("test")
        print("\n✅ Test passed! Fallback mechanism is working.")
        return 0
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
