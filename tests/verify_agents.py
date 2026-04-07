# tests/verify_agents.py
import asyncio
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from news_aggregator.agents.facts_summarizer import FactsSummarizer
from news_aggregator.config import AppConfig
from news_aggregator.fetcher.rss_fetcher import Article

# Load .env file
load_dotenv()


async def verify():
    print("--- Agents Verification (FactsSummarizer via OpenRouter) ---")

    # Check for API Key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("[SKIP] OPENROUTER_API_KEY not set in environment.")
        return

    # 1. Setup Config
    # We use environment variables directly to avoid validation alias issues
    os.environ["OPENROUTER_API_KEY"] = api_key
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        os.environ["TELEGRAM_BOT_TOKEN"] = "mock"
    if not os.getenv("TELEGRAM_CHAT_IDS"):
        os.environ["TELEGRAM_CHAT_IDS"] = "[123]"

    # Load from YAML and Environment
    config = AppConfig.load("config.yaml")

    # 2. Test Data
    article = Article(
        title="Fed Signals Rate Hold, Signals Two Cuts in 2026",
        source_url="https://example.com/fed-news",
        published_at=datetime.now(),
        feed_name="Mock Feed",
        author="Mock Author",
        summary_snippet=(
            "The Federal Reserve kept its benchmark interest rate unchanged at 4.25%-4.50% "
            "on Wednesday. Jerome Powell indicated that policymakers anticipate two "
            "quarter-point rate cuts by the end of 2026, citing cooling inflation data."
        ),
        category="macroeconomics",
    )

    # 3. Run Agent
    agent = FactsSummarizer(config)
    print(f"[RUNNING] FactsSummarizer on: '{article.title}'...")

    try:
        result = await agent.run(article)
        print("[OK] Agent returned result.")

        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError("Type %s not serializable" % type(obj))

        print(json.dumps(result, indent=2, default=json_serial))

        if "facts" in result and len(result["facts"]) > 0:
            print("[PASS] Facts extracted successfully.")
        else:
            print("[FAIL] No facts found in the response.")

    except Exception as e:
        print(f"[FAIL] Agent crashed: {str(e)}")


if __name__ == "__main__":
    asyncio.run(verify())
