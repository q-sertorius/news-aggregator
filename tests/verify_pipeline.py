# tests/verify_pipeline.py
import asyncio
import os
from dotenv import load_dotenv
from news_aggregator.pipeline.orchestrator import PipelineOrchestrator
from news_aggregator.config import AppConfig

# Load .env file
load_dotenv()

# Provide dummy values for Telegram if missing to allow pipeline test
if not os.getenv("TELEGRAM_BOT_TOKEN"):
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:ABC"
if not os.getenv("TELEGRAM_CHAT_IDS"):
    os.environ["TELEGRAM_CHAT_IDS"] = "[123, 456]"


async def verify():
    print("--- Pipeline Verification (Orchestrator via OpenRouter) ---")

    # Check for API Key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("[SKIP] OPENROUTER_API_KEY not set in environment.")
        return

    # 1. Setup Config
    config = AppConfig.load("config.yaml")
    config.feeds = config.feeds[:2]

    # 2. Initialize and Run
    orchestrator = PipelineOrchestrator(config, db_path="data/test_pipeline.db")
    await orchestrator.initialize()

    print(f"[RUNNING] Pipeline with feeds: {[f.url for f in config.feeds]}...")

    try:
        # Only process 2 articles for verification
        results = await orchestrator.run_pipeline(max_articles=2)

        if results:
            print(f"\n[PASS] Pipeline processed {len(results)} items successfully.")
            sample = results[0]
            print(f"Sample Result:")
            print(f" - Title: {sample['title']}")
            print(f" - Impact: {sample['impact']}")
        else:
            print("\n[OK] Pipeline completed, but no new articles were found.")

    except Exception as e:
        print(f"\n[FAIL] Pipeline crashed: {str(e)}")


if __name__ == "__main__":
    asyncio.run(verify())
