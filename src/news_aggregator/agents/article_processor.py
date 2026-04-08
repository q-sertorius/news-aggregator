# src/news_aggregator/agents/article_processor.py

import logging
from typing import Dict, Any, List
from .base import BaseAgent
from ..db.repository import NewsRepository
from ..fetcher.rss_fetcher import Article

logger = logging.getLogger(__name__)


class ArticleProcessor(BaseAgent):
    def __init__(self, config, repository: NewsRepository):
        super().__init__(config)
        self.repo = repository

    async def run(self, article: Article) -> Dict[str, Any]:
        """Process article in a single LLM call: extract facts, classify, analyze impact."""

        top_subjects = await self.repo.get_top_n_active_subjects(n=10)

        existing_subjects_text = ""
        if top_subjects:
            existing_subjects_text = (
                "Existing Active Subjects (ID, Name, Latest Status, Impact):\n"
            )
            for s in top_subjects:
                status_snippet = (
                    (s.get("latest_status", "")[:100] + "...")
                    if len(s.get("latest_status", "")) > 100
                    else s.get("latest_status", "")
                )
                existing_subjects_text += (
                    f'- ID: {s["id"]}, Name: "{s["name"]}", '
                    f'Status: "{status_snippet}", Impact: {s["impact_level"]}\n'
                )
            existing_subjects_text += "\n"
        else:
            existing_subjects_text = "No active subjects currently being tracked.\n\n"

        system_prompt = (
            "You are a news analysis engine. Process the given article in THREE steps and output a SINGLE JSON:\n"
            "1. EXTRACT: Pull out only verifiable facts, figures, entities.\n"
            "2. CLASSIFY: Given the 'Existing Active Subjects' below, determine if the new article "
            "is an 'ONGOING_DEVELOPMENT' of one of them (return its ID and update status). "
            "If it's a completely new, distinct topic, classify it as 'NEW_SUBJECT' "
            "and suggest a concise, descriptive name (max 10 words). Be aggressive about merging "
            "similar topics, favoring 'ONGOING_DEVELOPMENT' if a clear link exists to an active subject.\n"
            "3. ANALYZE: Assess market impact (HIGH/MEDIUM/LOW/NONE) of the article (or new subject if applicable) "
            "with affected assets (e.g., SPY, QQQ, AAPL, USD, Oil) and one-sentence reasoning.\n\n"
            "Output JSON with keys:\n"
            '  "facts": [list of fact strings],\n'
            '  "entities": [list of people/orgs],\n'
            '  "classification": "NEW_SUBJECT" or "ONGOING_DEVELOPMENT",\n'
            '  "subject_id": number or null (if NEW_SUBJECT),\n'
            '  "suggested_name": string (only if NEW_SUBJECT),\n'
            '  "status_update": one-line status summary for the subject (new or updated),\n'
            '  "impact_level": "HIGH", "MEDIUM", "LOW", or "NONE",\n'
            '  "affected_assets": [list of tickers/sectors],\n'
            '  "reasoning": one sentence on why this impact level.'
        )

        user_prompt = (
            f"{existing_subjects_text}"
            f"New Article:\n"
            f"  Title: {article.title}\n"
            f"  Feed: {article.feed_name}\n"
            f"  Category: {article.category}\n"
            f"  Content: {article.summary_snippet or 'N/A'}\n\n"
            "Return JSON only."
        )

        result = await self._call_llm(system_prompt, user_prompt, is_json=True)

        subject_id = result.get("subject_id")
        classification = result.get("classification", "NEW_SUBJECT")
        suggested_name = result.get("suggested_name")

        if classification == "NEW_SUBJECT" or not subject_id:
            name = suggested_name or article.title
            subject_id = await self.repo.get_or_create_subject(name, article.category)
            result["subject_id"] = subject_id
            result["classification"] = "NEW_SUBJECT"
            logger.info(f"[PROCESSOR] New subject created: '{name}' (ID: {subject_id})")
        else:
            if subject_id not in [
                s["id"] for s in top_subjects
            ] and not await self.repo.get_subject_by_id(subject_id):
                logger.warning(
                    f"[PROCESSOR] LLM suggested invalid subject_id {subject_id}. Creating new subject."
                )
                name = suggested_name or article.title
                subject_id = await self.repo.get_or_create_subject(
                    name, article.category
                )
                result["subject_id"] = subject_id
                result["classification"] = "NEW_SUBJECT"
            logger.info(f"[PROCESSOR] Matched subject ID {subject_id}")

        article_id = await self.repo.add_article(
            subject_id=subject_id,
            article_data={
                "title": article.title,
                "source_url": article.source_url,
                "published_at": article.published_at,
                "feed_name": article.feed_name,
                "author": article.author,
                "summary_snippet": article.summary_snippet,
            },
        )

        await self.repo.update_subject_status(
            subject_id=subject_id,
            status=result.get("status_update", ""),
            impact_level=result.get("impact_level", "NONE"),
            assets=result.get("affected_assets", []),
            article_id=article_id,
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
            "classification": result.get("classification"),
        }
