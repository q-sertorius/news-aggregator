# src/news_aggregator/main.py

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import ApplicationBuilder

from .config import AppConfig
from .pipeline.orchestrator import PipelineOrchestrator
from .telegram.bot import NewsBot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def run_once(orchestrator: PipelineOrchestrator, bot: NewsBot):
    """Execute a single pipeline cycle and send results."""
    try:
        results = await orchestrator.run_pipeline()
        if results:
            await bot.send_report(results)
    except Exception as e:
        logger.error(f"Pipeline run failed: {e}")


async def main():
    config = AppConfig.load("config.yaml")

    # Initialize orchestrator
    orchestrator = PipelineOrchestrator(config)
    await orchestrator.initialize()

    # Initialize bot with orchestrator reference
    bot = NewsBot(config, orchestrator=orchestrator)

    # Setup scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_once,
        "interval",
        minutes=config.polling.interval_minutes,
        args=[orchestrator, bot],
        id="news_pipeline",
        name="News Aggregator Pipeline",
        replace_existing=True,
    )
    scheduler.start()

    # Run a quick initial check
    logger.info("Running initial pipeline check...")
    await run_once(orchestrator, bot)

    # Start bot polling
    logger.info("Starting Telegram bot...")
    await bot.app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
