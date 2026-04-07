# src/news_aggregator/agents/context_tracker.py

import logging
from typing import List, Dict, Any, Optional
from .base import BaseAgent
from ..db.vector_store import VectorStore
from ..db.repository import NewsRepository

logger = logging.getLogger(__name__)


class ContextTracker(BaseAgent):
    def __init__(self, config, vector_store: VectorStore, repository: NewsRepository):
        super().__init__(config)
        self.vector_store = vector_store
        self.repo = repository

    async def run(self, fact_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Match fact summary to an existing subject or create a new one."""

        # 1. Build a rich search query from title + facts
        title = fact_summary.get("title", "")
        facts = ". ".join(fact_summary.get("facts", []))
        search_query = f"{title}. {facts}"

        candidates = await self.vector_store.find_similar_subjects(
            search_query, n_results=5
        )

        # 2. Filter candidates by distance threshold (cosine distance < 1.0 means some similarity)
        # For MiniLM, distance < 0.8 is usually a meaningful match
        close_matches = [c for c in candidates if c.get("distance", 1.0) < 0.85]

        # 3. Ask LLM to classify
        system_prompt = (
            "You are a news topic classifier. Your job is to DEDUPLICATE news subjects. "
            "Given a list of existing subjects and a new article, determine if this article "
            "is about the SAME ongoing event/topic as any existing subject. "
            "Be AGGRESSIVE about merging — if the article is about the same general topic "
            "as an existing subject, classify it as ONGOING_DEVELOPMENT. "
            "Only create NEW_SUBJECT if the article is clearly about a completely different topic. "
            "Output MUST be a JSON object with keys: 'classification' ('NEW_SUBJECT' or 'ONGOING_DEVELOPMENT'), "
            "'subject_id' (the ID of the best match, or null), 'suggested_name' (if new), 'status_update' (one-line summary)."
        )

        if close_matches:
            candidates_text = f"Close Matches (distance < 0.85):\n{close_matches}"
        elif candidates:
            candidates_text = f"Weak Matches (distance >= 0.85, consider merging if related):\n{candidates}"
        else:
            candidates_text = (
                "No existing subjects found. This is likely a NEW_SUBJECT."
            )

        user_prompt = (
            f"{candidates_text}\n\n"
            f"New Article:\n"
            f"  Title: {title}\n"
            f"  Facts: {facts}\n\n"
            "Return JSON only."
        )

        try:
            decision = await self._call_llm(system_prompt, user_prompt, is_json=True)

            # 4. Apply decision to Database
            subject_id = decision.get("subject_id")
            classification = decision.get("classification")

            if classification == "NEW_SUBJECT" or not subject_id:
                name = decision.get("suggested_name") or title
                subject_id = await self.repo.get_or_create_subject(
                    name, fact_summary.get("category", "general")
                )
                decision["subject_id"] = subject_id
                decision["classification"] = "NEW_SUBJECT"
                logger.info(
                    f"[TRACKER] New subject created: '{name}' (ID: {subject_id})"
                )
            else:
                logger.info(
                    f"[TRACKER] Matched existing subject ID {subject_id}: '{decision.get('status_update', '')}'"
                )

            # 5. Update vector store with the ACTUAL subject name (not suggested_name)
            # Fetch the real name from the repo
            subjects = await self.repo.get_active_subjects(limit=100)
            subject_name = title  # fallback
            for s in subjects:
                if s["id"] == subject_id:
                    subject_name = s["name"]
                    break

            await self.vector_store.add_subject(
                subject_id,
                subject_name,
                decision.get("status_update", ""),
            )

            return {
                "subject_id": subject_id,
                "status_update": decision.get("status_update"),
                "classification": decision["classification"],
            }

        except Exception as e:
            logger.error(f"ContextTracker failed: {str(e)}")
            raise e
