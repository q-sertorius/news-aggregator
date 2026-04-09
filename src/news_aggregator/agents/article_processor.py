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
                latest_status = s.get("latest_status") or ""
                status_snippet = (
                    (latest_status[:100] + "...")
                    if len(latest_status) > 100
                    else latest_status
                )
                existing_subjects_text += (
                    f'- ID: {s["id"]}, Name: "{s["name"]}", '
                    f'Status: "{status_snippet}", Impact: {s["impact_level"]}\n'
                )
            existing_subjects_text += "\n"
        else:
            existing_subjects_text = "No active subjects currently being tracked.\n\n"

        system_prompt = (
            "You are a strict news analysis JSON API. You must process the article and return ONLY a valid JSON object.\n\n"
            "RULES:\n"
            "1. EXTRACT: Find verifiable facts, figures, and entities.\n"
            "2. CLASSIFY: Compare the New Article to the Existing Active Subjects.\n"
            "   - If the article is about the EXACT SAME specific event/topic as an existing subject, set 'classification' to 'ONGOING_DEVELOPMENT' and provide its 'subject_id'.\n"
            "   - If it is a DIFFERENT event (e.g., do not merge a tech stock with geopolitics), set 'classification' to 'NEW_SUBJECT', 'subject_id' to null, and write a 'suggested_name' (max 10 words).\n"
            "3. STATUS UPDATE: Write a direct, factual news headline summarizing the article. DO NOT use meta-phrases like 'New subject tracking...', 'The article discusses...', or 'This is about...'. Just state the facts.\n"
            "4. ANALYZE: Assess market impact (HIGH, MEDIUM, LOW, or NONE) and provide a 1-sentence 'reasoning'.\n"
            "   - Use HIGH for major market-moving news (e.g., central bank policy shifts, major corporate earnings surprises, significant geopolitical conflicts).\
"
            "   - Use MEDIUM for moderately impactful news (e.g., sector-specific trends, minor economic data, smaller corporate announcements).\
"
            "   - Use LOW or NONE for minor news, speculative reports, or events with negligible market relevance.\
\n"
            "EXPECTED JSON FORMAT:\n"
            "{\n"
            '  "facts": ["fact 1", "fact 2"],\n'
            '  "entities": ["entity 1", "entity 2"],\n'
            '  "classification": "NEW_SUBJECT" or "ONGOING_DEVELOPMENT",\n'
            '  "subject_id": 123 or null,\n'
            '  "suggested_name": "Short Descriptive Topic Name",\n'
            '  "status_update": "Factual news summary of the article.",\n'
            '  "impact_level": "HIGH",\n'
            '  "reasoning": "Reason for impact."\n'
            "}"
        )

        user_prompt = (
            f"--- EXISTING ACTIVE SUBJECTS ---\n"
            f"{existing_subjects_text if top_subjects else 'None'}\n"
            f"--- NEW ARTICLE ---\n"
            f"Title: {article.title}\n"
            f"Feed: {article.feed_name}\n"
            f"Category: {article.category}\n"
            f"Content: {article.summary_snippet or 'N/A'}\n\n"
            "Analyze the New Article and output the JSON."
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
            article_id=article_id,
        )

        return {
            "title": article.title,
            "subject_id": subject_id,
            "status": result.get("status_update", ""),
            "impact": result.get("impact_level", "NONE"),
            "assets": [],  # Assets are no longer tracked in DB, but LLM might still generate them
            "reasoning": result.get("reasoning", ""),
            "url": article.source_url,
            "facts": result.get("facts", []),
            "classification": result.get("classification"),
        }
