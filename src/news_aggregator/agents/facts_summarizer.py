# src/news_aggregator/agents/facts_summarizer.py

from typing import Dict, Any, List
from .base import BaseAgent
from ..fetcher.rss_fetcher import Article


class FactsSummarizer(BaseAgent):
    async def run(self, article: Article) -> Dict[str, Any]:
        """Summarize an article into verifiable facts."""

        system_prompt = (
            "You are a financial news facts extractor. Extract ONLY verifiable facts, "
            "figures, dates, and direct statements from the article. Zero tolerance for "
            "opinions, speculation, editorializing, or emotional language. "
            "Output MUST be a JSON object with keys: 'facts' (array of strings), "
            "'numbers' (array of key figures), 'entities' (array of organizations/people)."
        )

        user_prompt = (
            f"Article Title: {article.title}\n"
            f"Published: {article.published_at}\n"
            f"Content: {article.summary_snippet}\n\n"
            "Return JSON only."
        )

        try:
            summary = await self._call_llm(system_prompt, user_prompt, is_json=True)
            # Attach metadata from the original article
            summary.update(
                {
                    "source_url": article.source_url,
                    "title": article.title,
                    "published_at": article.published_at,
                    "category": article.category,
                }
            )
            return summary
        except Exception as e:
            print(f"FactsSummarizer failed for {article.source_url}: {str(e)}")
            raise e
