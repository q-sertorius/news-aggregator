# src/news_aggregator/fetcher/rss_fetcher.py

import aiohttp
import feedparser
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel


class Article(BaseModel):
    title: str
    source_url: str
    published_at: Optional[datetime] = None
    feed_name: str
    author: Optional[str] = None
    summary_snippet: Optional[str] = None
    category: str


class RSSFetcher:
    def __init__(self, timeout_seconds: int = 10):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def fetch_feed(self, url: str, category: str) -> List[Article]:
        """Fetch and parse a single RSS feed."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        print(f"Error fetching {url}: Status {response.status}")
                        return []

                    xml_content = await response.text()
                    # feedparser doesn't support async, but parsing is usually fast
                    # for very large feeds, we could run this in a threadpool
                    parsed_feed = feedparser.parse(xml_content)

                    articles = []
                    feed_title = parsed_feed.feed.get("title", url)

                    for entry in parsed_feed.entries:
                        published = None
                        if (
                            hasattr(entry, "published_parsed")
                            and entry.published_parsed
                        ):
                            published = datetime(*entry.published_parsed[:6])
                        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                            published = datetime(*entry.updated_parsed[:6])

                        articles.append(
                            Article(
                                title=entry.get("title", "No Title"),
                                source_url=entry.get("link", ""),
                                published_at=published,
                                feed_name=feed_title,
                                author=entry.get("author"),
                                summary_snippet=entry.get("summary", "")[
                                    :500
                                ],  # Truncate early
                                category=category,
                            )
                        )

                    return articles
        except Exception as e:
            print(f"Failed to fetch feed {url}: {str(e)}")
            return []

    async def fetch_all(self, feed_configs: List[Dict[str, str]]) -> List[Article]:
        """Fetch multiple feeds in parallel."""
        tasks = [
            self.fetch_feed(config["url"], config["category"])
            for config in feed_configs
        ]
        results = await asyncio.gather(*tasks)

        # Flatten list of lists
        return [article for sublist in results for article in sublist]
