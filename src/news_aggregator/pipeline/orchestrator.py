# src/news_aggregator/pipeline/orchestrator.py

import asyncio
import time
import logging
import os
from typing import List, Dict, Any, Optional
from ..config import AppConfig
from ..db.repository import NewsRepository
from ..fetcher.rss_fetcher import RSSFetcher
from ..fetcher.deduplicator import Deduplicator
from ..agents.article_processor import ArticleProcessor

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, config: AppConfig, db_path: str = "data/news_aggregator.db"):
        self.config = config

        # --- FIX: Delete existing DB to ensure schema is updated ---
        if os.path.exists(db_path):
            logger.warning(
                f"Removing existing database file at '{db_path}' to ensure schema is up-to-date."
            )
            os.remove(db_path)
        # --- END FIX ---

        self.repo = NewsRepository(db_path=db_path)
        self.fetcher = RSSFetcher()
        self.dedup = Deduplicator(self.repo)
        self.processor = ArticleProcessor(config, self.repo)

    async def initialize(self):
        """Create tables and indexes if they don't exist."""
        await self.repo.initialize()
        logger.info("[INIT] SQLite initialized.")

    async def run_pipeline(self, max_articles: int = None) -> List[Dict[str, Any]]:
        """Run a single polling cycle of the news aggregator."""
        start_time = time.time()
        logger.info(
            f"\n--- Starting Pipeline Run: {time.strftime('%Y-%m-%d %H:%M:%S')} ---"
        )

        # 1. Fetch all news
        logger.info(f"[FETCH] Polling {len(self.config.feeds)} RSS feeds...")
        raw_articles = await self.fetcher.fetch_all(
            [f.model_dump() for f in self.config.feeds]
        )
        logger.info(f"[FETCH] Retrieved {len(raw_articles)} total articles.\n")

        # 2. Deduplicate
        new_articles = await self.dedup.filter_new_articles(raw_articles)

        if max_articles:
            new_articles = new_articles[:max_articles]

        logger.info(f"[DEDUP] {len(new_articles)} new articles to process.")

        if not new_articles:
            logger.info("[DEDUP] No new articles. Ending run early.")
            return []

        results = []
        processed_count = 0

        for article in new_articles:
            try:
                logger.info(
                    f"[PROCESS] Article {processed_count + 1}/{len(new_articles)}: '{article.title[:50]}...'"
                )

                result = await self.processor.run(article)
                results.append(result)
                processed_count += 1

            except Exception as e:
                logger.error(
                    f"[ERROR] Failed to process article '{article.title[:30]}': {e}",
                    exc_info=True,  # Log full traceback for better debugging
                )
                await self.repo.add_to_dead_letter(
                    article.source_url, article.summary_snippet or "", str(e)
                )
                continue

        duration = time.time() - start_time
        logger.info(f"\n--- Pipeline Run Complete ({duration:.1f}s) ---")
        logger.info(f"[METRICS] Articles Processed: {processed_count}")
        logger.info(
            f"[METRICS] Impactful Subjects Detected: {len([r for r in results if r['impact'] != 'NONE'])}"
        )

        return results
