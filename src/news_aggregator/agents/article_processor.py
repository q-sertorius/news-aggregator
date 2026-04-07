# src/news_aggregator/agents/article_processor.py
"""
Combined agent that processes an article in a SINGLE LLM call:
1. Extracts key facts
2. Classifies to existing subject or creates new one
3. Analyzes market impact
"""

import logging
from typing import Dict, Any, List
from .base import BaseAgent
from ..db.vector_store import VectorStore
from ..db.repository import NewsRepository
from ..fetcher.rss_fetcher import Article

logger = logging.getLogger(__name__)


class ArticleProcessor(BaseAgent):
    def __init__(self, config, vector_store: VectorStore, repository: NewsRepository):
        super().__init__(config)
        self.vector_store = vector_store
        self.repo = repository

    async def run(self, article: Article) -> Dict[str, Any]:
        """Process article in a single LLM call: extract facts, classify, analyze impact."""

        # 1. Vector search for candidate subjects
        candidates = await self.vector_store.find_similar_subjects(
            f"{article.title}. {article.summary_snippet or ''}",
            n_results=5,
        )

        close_matches = [c for c in candidates if c.get("distance", 1.0) < 0.85]

        if close_matches:
            candidates_text = f"Close Matches:\n{close_matches}"
        elif candidates:
            candidates_text = (
                f"Weak Matches (consider merging if related):\n{candidates}"
            )
        else:
            candidates_text = "No existing subjects."

        # 2. Single combined prompt
        system_prompt = (
            "You are a news analysis engine. Process the given article in THREE steps and output a SINGLE JSON:\n"
            "1. EXTRACT: Pull out only verifiable facts, figures, entities.\n"
            "2. CLASSIFY: Match to an existing subject or flag as NEW_SUBJECT. Be aggressive about merging.\n"
            "3. ANALYZE: Assess market impact (HIGH/MEDIUM/LOW/NONE) with affected assets and reasoning.\n\n"
            "Output JSON with keys:\n"
            '  "facts": [list of fact strings],\n'
            '  "entities": [list of people/orgs],\n'
            '  "classification": "NEW_SUBJECT" or "ONGOING_DEVELOPMENT",\n'
            '  "subject_id": number or null,\n'
            '  "suggested_name": string (only if new),\n'
            '  "status_update": one-line status summary,\n'
            '  "impact_level": "HIGH", "MEDIUM", "LOW", or "NONE",\n'
            '  "affected_assets": [list of tickers/sectors],\n'
            '  "reasoning": one sentence on why this impact level.'
        )

        user_prompt = (
            f"{candidates_text}\n\n"
            f"Article:\n"
            f"  Title: {article.title}\n"
            f"  Feed: {article.feed_name}\n"
            f"  Category: {article.category}\n"
            f"  Content: {article.summary_snippet or 'N/A'}\n\n"
            "Return JSON only."
        )

        result = await self._call_llm(system_prompt, user_prompt, is_json=True)

        # 3. Apply classification to database
        subject_id = result.get("subject_id")
        classification = result.get("classification", "NEW_SUBJECT")

        if classification == "NEW_SUBJECT" or not subject_id:
            name = result.get("suggested_name") or article.title
            subject_id = await self.repo.get_or_create_subject(name, article.category)
            result["subject_id"] = subject_id
            result["classification"] = "NEW_SUBJECT"
            logger.info(f"[PROCESSOR] New subject: '{name}' (ID: {subject_id})")
        else:
            logger.info(f"[PROCESSOR] Matched subject ID {subject_id}")

        # 4. Update vector store with real subject name
        subjects = await self.repo.get_active_subjects(limit=100)
        subject_name = article.title
        for s in subjects:
            if s["id"] == subject_id:
                subject_name = s["name"]
                break

        await self.vector_store.add_subject(
            subject_id, subject_name, result.get("status_update", "")
        )

        # 5. Update subject status and impact in SQLite
        await self.repo.update_subject_status(
            subject_id=subject_id,
            status=result.get("status_update", ""),
            impact_level=result.get("impact_level", "NONE"),
            assets=result.get("affected_assets", []),
        )

        # 6. Save article
        await self.repo.add_article(
            subject_id,
            {
                "title": article.title,
                "source_url": article.source_url,
                "published_at": article.published_at,
                "feed_name": article.feed_name,
                "author": article.author,
                "summary_snippet": article.summary_snippet,
            },
        )

        return {
            "title": article.title,
            "subject_id": subject_id,
            "status": result.get("status_update", ""),
            "impact": result.get("impact_level", "NONE"),
            "assets": result.get("affected_assets", []),
            "reasoning": result.get("reasoning", ""),
            "url": article.source_url,
            "facts": result.get("facts", []),
        }
