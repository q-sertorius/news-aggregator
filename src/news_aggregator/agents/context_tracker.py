# src/news_aggregator/agents/context_tracker.py

from typing import List, Dict, Any, Optional
from .base import BaseAgent
from ..db.vector_store import VectorStore
from ..db.repository import NewsRepository


class ContextTracker(BaseAgent):
    def __init__(self, config, vector_store: VectorStore, repository: NewsRepository):
        super().__init__(config)
        self.vector_store = vector_store
        self.repo = repository

    async def run(self, fact_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Match fact summary to an existing subject or create a new one."""

        # 1. Get candidates from Vector Store
        fact_text = ". ".join(fact_summary.get("facts", []))
        candidates = await self.vector_store.find_similar_subjects(
            fact_text, n_results=3
        )

        # 2. Ask Gemini to classify
        system_prompt = (
            "You are a news topic classifier. Given a few potentially relevant subjects and a new fact summary, "
            "match the fact to the most relevant subject or flag it as NEW_SUBJECT. "
            "Output MUST be a JSON object with keys: 'classification' ('NEW_SUBJECT' or 'ONGOING_DEVELOPMENT'), "
            "'subject_id' (the ID of the match, or null), 'suggested_name' (if new), 'status_update' (one-line summary)."
        )

        user_prompt = (
            f"Relevant Subjects: {candidates}\n\n"
            f"New Fact Summary: {fact_summary}\n\n"
            "Return JSON only."
        )

        try:
            decision = await self._call_llm(system_prompt, user_prompt, is_json=True)

            # 3. Apply decision to Database
            subject_id = decision.get("subject_id")
            classification = decision.get("classification")

            if classification == "NEW_SUBJECT" or not subject_id:
                name = decision.get("suggested_name") or fact_summary.get("title")
                subject_id = await self.repo.get_or_create_subject(
                    name, fact_summary.get("category", "general")
                )
                decision["subject_id"] = subject_id
                decision["classification"] = "NEW_SUBJECT"

            # Update vector store with latest info
            await self.vector_store.add_subject(
                subject_id,
                decision.get("suggested_name", "Unknown"),
                decision.get("status_update", ""),
            )

            # Update SQLite with the new article link
            # (In a full pipeline, we would link the article ID here)

            return {
                "subject_id": subject_id,
                "status_update": decision.get("status_update"),
                "classification": decision["classification"],
            }

        except Exception as e:
            print(f"ContextTracker failed: {str(e)}")
            raise e
