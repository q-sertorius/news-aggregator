# src/news_aggregator/main.py

import asyncio
import logging

from .config import AppConfig
from .pipeline.orchestrator import PipelineOrchestrator
from .db.repository import NewsRepository
from .db.vector_store import VectorStore
from .web.server import WebDashboard

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    config = AppConfig.load("config.yaml")

    # Initialize data layer
    repo = NewsRepository()
    await repo.initialize()

    vstore = VectorStore()

    # Initialize orchestrator
    orchestrator = PipelineOrchestrator(config)
    await orchestrator.initialize()

    # Start web dashboard (Telegram kept but disabled)
    dashboard = WebDashboard(orchestrator, repo, vstore)
    dashboard.run(host="127.0.0.1", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
