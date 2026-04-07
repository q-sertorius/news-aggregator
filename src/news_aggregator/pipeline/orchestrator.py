# src/news_aggregator/pipeline/orchestrator.py

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional
from ..config import AppConfig
from ..db.repository import NewsRepository
from ..db.vector_store import VectorStore
from ..fetcher.rss_fetcher import RSSFetcher
from ..fetcher.deduplicator import Deduplicator
from ..agents.article_processor import ArticleProcessor

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, config: AppConfig, db_path: str = "data/news_aggregator.db"):
        self.config = config
        self.repo = NewsRepository(db_path=db_path)
        self.vstore = VectorStore()
        self.fetcher = RSSFetcher()
        self.dedup = Deduplicator(self.repo)

        # Single combined agent: extracts facts, classifies, analyzes impact in 1 LLM call
        self.processor = ArticleProcessor(config, self.vstore, self.repo)

    async def initialize(self):
        """Initialize database and vector store."""
        await self.repo.initialize()
        logger.info("[INIT] SQLite and Vector Store initialized.")

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
        logger.info(f"[FETCH] Retrieved {len(raw_articles)} total articles.")

        # 2. Deduplicate
        new_articles = await self.dedup.filter_new_articles(raw_articles)

        # Optional cap for quick testing, but default = process all
        if max_articles:
            new_articles = new_articles[:max_articles]

        logger.info(f"[DEDUP] {len(new_articles)} new articles to process.")

        if not new_articles:
            logger.info("[DEDUP] No new articles. Ending run early.")
            return []

        # 3. Process each article — 1 LLM call per article (was 3)
        # Rate limiting: openrouter/free has ~15 RPM.
        # We wait 4s between calls to stay under 15/min.
        results = []
        processed_count = 0
        call_delay = 60.0 / self.config.llm.rate_limit_rpm  # ~4s at 15 RPM

        for article in new_articles:
            try:
                logger.info(
                    f"[PROCESS] Article {processed_count + 1}/{len(new_articles)}: '{article.title[:50]}...'"
                )

                # Single call: extract + classify + analyze
                result = await self.processor.run(article)
                results.append(result)
                processed_count += 1

                # Rate limit between articles
                if processed_count < len(new_articles):
                    await asyncio.sleep(call_delay)

            except Exception as e:
                logger.error(
                    f"[ERROR] Failed to process article '{article.title[:30]}': {str(e)}"
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
