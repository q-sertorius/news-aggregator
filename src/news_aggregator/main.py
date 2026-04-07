# src/news_aggregator/main.py

import asyncio
import logging

from .config import AppConfig
from .pipeline.orchestrator import PipelineOrchestrator
from .web.server import WebDashboard

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    config = AppConfig.load("config.yaml")

    # Initialize orchestrator (creates repo + vstore internally)
    logger.info("Initializing orchestrator...")
    orchestrator = PipelineOrchestrator(config)
    await orchestrator.initialize()

    # Start web dashboard
    logger.info("Starting web dashboard...")
    dashboard = WebDashboard(
        orchestrator,
        orchestrator.repo,
        orchestrator.vstore,
    )
    await dashboard.run(host="127.0.0.1", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
