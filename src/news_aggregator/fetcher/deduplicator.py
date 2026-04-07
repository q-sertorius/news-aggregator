# src/news_aggregator/fetcher/deduplicator.py

from typing import List
from ..fetcher.rss_fetcher import Article
from ..db.repository import NewsRepository


class Deduplicator:
    def __init__(self, repository: NewsRepository):
        self.repo = repository

    async def filter_new_articles(self, articles: List[Article]) -> List[Article]:
        """Filter out articles that have already been processed in the database."""
        # For simplicity, we check if each source_url exists in the articles table.
        # In a real system, we'd use a fast Bloom filter or a set in memory
        # for a cache and then check the DB.

        # Collect all unique URLs to check
        urls_to_check = list(set([a.source_url for a in articles if a.source_url]))

        # Check database for existing articles
        existing_urls = await self.repo.check_existing_urls(urls_to_check)

        # Return only articles that don't exist
        return [a for a in articles if a.source_url not in existing_urls]
