# src/news_aggregator/db/repository.py

import aiosqlite
import json
import os
from datetime import datetime, timezone
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
                (name, category, datetime.now(timezone.utc)),
            )
            await db.commit()
            return cursor.lastrowid

    async def add_article(self, subject_id: int, article_data: Dict[str, Any]) -> int:
        """Insert a new article into the database."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO articles 
                (subject_id, title, source_url, published_at, feed_name, author, summary_snippet, fetched_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    subject_id,
                    article_data["title"],
                    article_data["source_url"],
                    article_data.get("published_at"),
                    article_data.get("feed_name"),
                    article_data.get("author"),
                    article_data.get("summary_snippet"),
                    datetime.now(timezone.utc),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_subject_status(
        self,
        subject_id: int,
        status: str,
        impact_level: str,
        article_id: int,
    ):
        """Update a subject's status, impact level, and associated assets."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE subjects SET latest_status = ?, impact_level = ?, last_seen = ? WHERE id = ?",
                (
                    status,
                    impact_level,
                    datetime.now(timezone.utc),
                    subject_id,
                ),
            )

            cursor = await db.execute(
                "INSERT INTO subject_history (subject_id, article_id, status_snapshot, impact_level, updated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    subject_id,
                    article_id,
                    status,
                    impact_level,
                    datetime.now(timezone.utc),
                ),
            )
            history_id = cursor.lastrowid
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
            return [
                {
                    k: v.isoformat() + "Z" if isinstance(v, datetime) else v
                    for k, v in dict(row).items()
                }
                for row in rows
            ]

    async def check_existing_urls(self, urls: List[str]) -> List[str]:
        """Given a list of URLs, return the ones that already exist in the articles table."""
        if not urls:
            return []

        async with aiosqlite.connect(self.db_path) as db:
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
                "INSERT INTO dead_letter_queue (source_url, raw_content, error_message, failed_at) VALUES (?, ?, ?, ?)",
                (url, content, error, datetime.now(timezone.utc)),
            )
            await db.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
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
            last_article_fetched_at = await (
                await db.execute("SELECT MAX(fetched_at) as t FROM articles")
            ).fetchone()
            last_dead_letter_failed_at = await (
                await db.execute("SELECT MAX(failed_at) as t FROM dead_letter_queue")
            ).fetchone()

            last_poll = last_article_fetched_at["t"]
            if last_poll and isinstance(last_poll, str):
                last_poll = (
                    datetime.fromisoformat(last_poll.replace("Z", "+00:00")).isoformat()
                    + "Z"
                )

            last_failed = last_dead_letter_failed_at["t"]
            if last_failed and isinstance(last_failed, str):
                last_failed = (
                    datetime.fromisoformat(
                        last_failed.replace("Z", "+00:00")
                    ).isoformat()
                    + "Z"
                )

            return {
                "subjects": subjects["c"],
                "articles": articles["c"],
                "dead_letters": dead["c"],
                "last_poll": last_poll or "Never",
                "last_failed": last_failed or "Never",
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
            return [
                {
                    k: v.isoformat() + "Z" if isinstance(v, datetime) else v
                    for k, v in dict(row).items()
                }
                for row in rows
            ]

    async def get_dead_letters(self, limit: int = 20) -> List[Dict]:
        """Fetch recent failed articles."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM dead_letter_queue ORDER BY failed_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    k: v.isoformat() + "Z" if isinstance(v, datetime) else v
                    for k, v in dict(row).items()
                }
                for row in rows
            ]

    async def get_latest_article_for_subject(self, subject_id: int) -> Optional[Dict]:
        """Get the most recent article for a subject."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT a.id, a.title, a.source_url, a.feed_name, a.published_at, a.fetched_at,
                          s.name as subject_name, s.impact_level
                   FROM articles a
                   LEFT JOIN subjects s ON a.subject_id = s.id
                   WHERE a.subject_id = ?
                   ORDER BY a.fetched_at DESC LIMIT 1""",
                (subject_id,),
            )
            row = await cursor.fetchone()
            if row:
                d = {
                    k: v.isoformat() + "Z" if isinstance(v, datetime) else v
                    for k, v in dict(row).items()
                }
                assets_cursor = await db.execute(
                    "SELECT asset_ticker FROM subject_assets WHERE subject_id = ?",
                    (subject_id,),
                )
                asset_rows = await assets_cursor.fetchall()
                d["assets"] = [r["asset_ticker"] for r in asset_rows]
                d["reasoning"] = ""
                d["classification"] = "ONGOING_DEVELOPMENT"
                return d
            return None

    async def get_subject_by_id(self, subject_id: int) -> Optional[Dict]:
        """Fetch a subject by its ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM subjects WHERE id = ?", (subject_id,)
            )
            row = await cursor.fetchone()
            if row:
                d = {
                    k: v.isoformat() + "Z" if isinstance(v, datetime) else v
                    for k, v in dict(row).items()
                }
                return d
            return None

    async def get_top_n_active_subjects(self, n: int = 10) -> List[Dict]:
        """Fetch the top N most impactful and recently active subjects."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    s.id, s.name, s.category, s.latest_status, s.impact_level, s.last_seen
                FROM subjects s
                ORDER BY
                    CASE s.impact_level
                        WHEN 'HIGH' THEN 1
                        WHEN 'MEDIUM' THEN 2
                        WHEN 'LOW' THEN 3
                        ELSE 4
                    END,
                    s.last_seen DESC
                LIMIT ?
                """,
                (n,),
            )
            rows = await cursor.fetchall()
            formatted_subjects = []
            for row in rows:
                d = dict(row)
                if isinstance(d["last_seen"], datetime):
                    d["last_seen"] = d["last_seen"].isoformat() + "Z"
                formatted_subjects.append(d)
            return formatted_subjects

    async def get_subject_history(self, subject_id: int, limit: int = 10) -> List[Dict]:
        """Fetch the latest N status updates for a specific subject."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT sh.id, sh.status_snapshot, sh.impact_level, sh.updated_at,
                       a.title as article_title, a.source_url as article_source_url
                FROM subject_history sh
                LEFT JOIN articles a ON sh.article_id = a.id
                WHERE sh.subject_id = ?
                ORDER BY sh.updated_at DESC
                LIMIT ?
                """,
                (subject_id, limit),
            )
            rows = await cursor.fetchall()
            return [
                {
                    k: v.isoformat() + "Z" if isinstance(v, datetime) else v
                    for k, v in dict(row).items()
                }
                for row in rows
            ]

    async def clear_all(self):
        """Delete all data from all tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM subject_assets")
            await db.execute("DELETE FROM history_articles")
            await db.execute("DELETE FROM subject_history")
            await db.execute("DELETE FROM articles")
            await db.execute("DELETE FROM subjects")
            await db.execute("DELETE FROM dead_letter_queue")
            await db.execute("DELETE FROM watchlist")
            await db.commit()
