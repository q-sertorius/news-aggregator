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
from ..agents.facts_summarizer import FactsSummarizer
from ..agents.context_tracker import ContextTracker
from ..agents.impact_analyzer import ImpactAnalyzer

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, config: AppConfig, db_path: str = "data/news_aggregator.db"):
        self.config = config
        self.repo = NewsRepository(db_path=db_path)
        self.vstore = VectorStore()
        self.fetcher = RSSFetcher()
        self.dedup = Deduplicator(self.repo)

        # Agents
        self.summarizer = FactsSummarizer(config)
        self.tracker = ContextTracker(config, self.vstore, self.repo)
        self.analyzer = ImpactAnalyzer(config, self.repo)

    async def initialize(self):
        """Initialize database and vector store."""
        await self.repo.initialize()
        logger.info("[INIT] SQLite and Vector Store initialized.")

    async def run_pipeline(self, max_articles: int = None) -> List[Dict[str, Any]]:
        """Run a single polling cycle of the news aggregator."""
        start_time = time.time()
        print(f"\n--- Starting Pipeline Run: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

        # 1. Fetch all news
        print(f"[FETCH] Polling {len(self.config.feeds)} RSS feeds...")
        raw_articles = await self.fetcher.fetch_all(
            [f.model_dump() for f in self.config.feeds]
        )
        print(f"[FETCH] Retrieved {len(raw_articles)} total articles.")

        # 2. Deduplicate
        new_articles = await self.dedup.filter_new_articles(raw_articles)

        if max_articles:
            new_articles = new_articles[:max_articles]

        print(f"[DEDUP] Identified {len(new_articles)} new articles to process.")

        if not new_articles:
            print("[DEDUP] No new articles. Ending run early.")
            return []

        # 3. Process each article through the agent pipeline
        # We process sequentially or with small batches to respect Gemini's 15 RPM limit
        results = []
        processed_count = 0

        for article in new_articles:
            try:
                print(
                    f"\n[PROCESS] Article {processed_count + 1}/{len(new_articles)}: '{article.title[:50]}...'"
                )

                # Step A: Summarize Facts
                fact_summary = await self.summarizer.run(article)
                print(f"[DEBUG] Fact summary: {fact_summary}")

                # Step B: Contextualize (Match to Subject)
                context_result = await self.tracker.run(fact_summary)

                # Step C: Impact Analysis
                impact_result = await self.analyzer.run(
                    context_result["subject_id"], context_result["status_update"]
                )

                # Link article to subject in database
                await self.repo.add_article(context_result["subject_id"], fact_summary)

                results.append(
                    {
                        "title": article.title,
                        "subject_id": context_result["subject_id"],
                        "status": context_result["status_update"],
                        "impact": impact_result["impact_level"],
                        "assets": impact_result["affected_assets"],
                        "reasoning": impact_result["reasoning"],
                        "url": article.source_url,
                    }
                )

                processed_count += 1

                # Respect Rate Limits (15 RPM max for Gemini Flash free tier)
                # Each article uses ~3 LLM calls. At 25 articles, that's 75 calls.
                # 15 RPM = 1 call every 4 seconds.
                # To be safe, we wait between articles.
                if processed_count < len(new_articles):
                    await asyncio.sleep(4)  # 4s delay between articles

            except Exception as e:
                import traceback

                print(
                    f"[ERROR] Failed to process article '{article.title[:30]}': {str(e)}"
                )
                traceback.print_exc()
                # Log to dead letter

                await self.repo.add_to_dead_letter(
                    article.source_url, article.summary_snippet or "", str(e)
                )
                continue

        duration = time.time() - start_time
        print(f"\n--- Pipeline Run Complete ({duration:.1f}s) ---")
        print(f"[METRICS] Articles Processed: {processed_count}")
        print(
            f"[METRICS] Impactful Subjects Detected: {len([r for r in results if r['impact'] != 'NONE'])}"
        )

        return results
