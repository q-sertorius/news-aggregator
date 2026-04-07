# tests/verify_phase2.py
import asyncio
import os
from news_aggregator.fetcher.rss_fetcher import RSSFetcher
from news_aggregator.fetcher.deduplicator import Deduplicator
from news_aggregator.db.repository import NewsRepository


async def verify():
    print("--- Phase 2 Verification ---")

    # 1. Initialize
    db_path = "data/test_news_v2.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    repo = NewsRepository(db_path=db_path)
    await repo.initialize()
    fetcher = RSSFetcher()
    dedup = Deduplicator(repo)

    # 2. Fetch from a real feed
    test_feed = {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "geopolitics",
    }
    print(f"[FETCHING] {test_feed['url']}...")
    articles = await fetcher.fetch_all([test_feed])

    if not articles:
        print("[FAIL] No articles fetched. Check internet or feed URL.")
        return

    print(f"[OK] Fetched {len(articles)} articles.")

    # 3. Test Deduplication (First Run - should all be new)
    new_articles = await dedup.filter_new_articles(articles)
    print(f"[OK] First Pass: {len(new_articles)}/{len(articles)} identified as new.")

    if len(new_articles) != len(articles):
        print("[FAIL] First pass should identify all as new (empty DB).")
        return

    # 4. Add some to DB to test filtering
    subject_id = await repo.get_or_create_subject("World News", "geopolitics")
    test_article = articles[0]
    await repo.add_article(subject_id, test_article.model_dump())
    print(f"[OK] Added one article to DB: '{test_article.title[:40]}...'")

    # 5. Test Deduplication (Second Run - should filter out the one we added)
    filtered_articles = await dedup.filter_new_articles(articles)
    print(
        f"[OK] Second Pass: {len(filtered_articles)}/{len(articles)} identified as new."
    )

    if len(filtered_articles) == len(articles) - 1:
        print("[PASS] Deduplication correctly filtered out the existing article.")
    else:
        print(
            f"[FAIL] Deduplication failed. Expected {len(articles) - 1}, got {len(filtered_articles)}."
        )


if __name__ == "__main__":
    asyncio.run(verify())
