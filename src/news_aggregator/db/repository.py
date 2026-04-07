# src/news_aggregator/db/repository.py

import aiosqlite
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from .models import CREATE_TABLES_SQL


class NewsRepository:
    def __init__(self, db_path: str = "data/news_aggregator.db"):
        self.db_path = db_path

    async def initialize(self):
        """Create tables and indexes if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.commit()

    async def get_or_create_subject(self, name: str, category: str) -> int:
        """Find subject by name or create a new one."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT id FROM subjects WHERE name = ?", (name,))
            row = await cursor.fetchone()
            if row:
                return row["id"]

            cursor = await db.execute(
                "INSERT INTO subjects (name, category, last_seen) VALUES (?, ?, ?)",
                (name, category, datetime.now()),
            )
            await db.commit()
            return cursor.lastrowid

    async def add_article(self, subject_id: int, article_data: Dict[str, Any]) -> int:
        """Insert a new article into the database."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO articles 
                (subject_id, title, source_url, published_at, feed_name, author, summary_snippet) 
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    subject_id,
                    article_data["title"],
                    article_data["source_url"],
                    article_data.get("published_at"),
                    article_data.get("feed_name"),
                    article_data.get("author"),
                    article_data.get("summary_snippet"),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_subject_status(
        self, subject_id: int, status: str, impact_level: str, assets: List[str]
    ):
        """Update a subject's status, impact level, and associated assets."""
        async with aiosqlite.connect(self.db_path) as db:
            # Update subject metadata
            await db.execute(
                "UPDATE subjects SET latest_status = ?, impact_level = ?, last_seen = ? WHERE id = ?",
                (status, impact_level, datetime.now(), subject_id),
            )

            # Update history
            cursor = await db.execute(
                "INSERT INTO subject_history (subject_id, status_snapshot, impact_level) VALUES (?, ?, ?)",
                (subject_id, status, impact_level),
            )
            history_id = cursor.lastrowid

            # Update assets (clear and re-add for simplicity)
            await db.execute(
                "DELETE FROM subject_assets WHERE subject_id = ?", (subject_id,)
            )
            for asset in assets:
                await db.execute(
                    "INSERT INTO subject_assets (subject_id, asset_ticker) VALUES (?, ?)",
                    (subject_id, asset),
                )

            await db.commit()
            return history_id

    async def get_active_subjects(self, limit: int = 50) -> List[Dict]:
        """Fetch active subjects for context tracking."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM subjects ORDER BY last_seen DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def check_existing_urls(self, urls: List[str]) -> List[str]:
        """Given a list of URLs, return the ones that already exist in the articles table."""
        if not urls:
            return []

        async with aiosqlite.connect(self.db_path) as db:
            # Using placeholders for a safe IN clause
            placeholders = ",".join(["?"] * len(urls))
            cursor = await db.execute(
                f"SELECT source_url FROM articles WHERE source_url IN ({placeholders})",
                urls,
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def add_to_dead_letter(self, url: str, content: str, error: str):
        """Log a failed article for manual inspection."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO dead_letter_queue (source_url, raw_content, error_message) VALUES (?, ?, ?)",
                (url, content, error),
            )
            await db.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics for the /status command."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            subjects = await (
                await db.execute("SELECT COUNT(*) as c FROM subjects")
            ).fetchone()
            articles = await (
                await db.execute("SELECT COUNT(*) as c FROM articles")
            ).fetchone()
            dead = await (
                await db.execute("SELECT COUNT(*) as c FROM dead_letter_queue")
            ).fetchone()
            last = await (
                await db.execute("SELECT MAX(fetched_at) as t FROM articles")
            ).fetchone()
            return {
                "subjects": subjects["c"],
                "articles": articles["c"],
                "dead_letters": dead["c"],
                "last_poll": last["t"] or "Never",
            }

    async def get_recent_articles(self, limit: int = 20) -> List[Dict]:
        """Fetch recent articles with subject info."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT a.id, a.title, a.source_url, a.feed_name, a.published_at, a.fetched_at,
                          s.name as subject_name, s.impact_level
                   FROM articles a
                   LEFT JOIN subjects s ON a.subject_id = s.id
                   ORDER BY a.fetched_at DESC LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_dead_letters(self, limit: int = 20) -> List[Dict]:
        """Fetch recent failed articles."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM dead_letter_queue ORDER BY failed_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_recent_articles(self, limit: int = 20) -> List[Dict]:
        """Fetch recent articles with subject info."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT a.id, a.title, a.source_url, a.feed_name, a.published_at, a.fetched_at,
                          s.name as subject_name, s.impact_level
                   FROM articles a
                   LEFT JOIN subjects s ON a.subject_id = s.id
                   ORDER BY a.fetched_at DESC LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_dead_letters(self, limit: int = 20) -> List[Dict]:
        """Fetch recent failed articles."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM dead_letter_queue ORDER BY failed_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
