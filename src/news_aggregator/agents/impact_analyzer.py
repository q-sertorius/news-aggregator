# src/news_aggregator/agents/impact_analyzer.py

from typing import List, Dict, Any, Optional
from .base import BaseAgent
from ..db.repository import NewsRepository


class ImpactAnalyzer(BaseAgent):
    def __init__(self, config, repository: NewsRepository):
        super().__init__(config)
        self.repo = repository

    async def run(self, subject_id: int, status_update: str) -> Dict[str, Any]:
        """Evaluate market impact for a given subject update."""

        system_prompt = (
            "You are an investment impact analyst. Evaluate the given news subject for potential "
            "impact on financial markets (equities primary, then forex, bonds, commodities). "
            "Output MUST be a JSON object with keys: 'impact_level' ('HIGH', 'MEDIUM', 'LOW', 'NONE'), "
            "'affected_assets' (array of tickers/sectors like SPY, QQQ, AAPL, USD, Oil, XLF), "
            "'reasoning' (one sentence explaining why)."
        )

        user_prompt = (
            f"Subject Update: {status_update}\n"
            f"Subject ID: {subject_id}\n\n"
            "Return JSON only."
        )

        try:
            impact_result = await self._call_llm(
                system_prompt, user_prompt, is_json=True
            )

            # Update database with impact result
            await self.repo.update_subject_status(
                subject_id=subject_id,
                status=status_update,
                impact_level=impact_result.get("impact_level", "NONE"),
                assets=impact_result.get("affected_assets", []),
            )

            return {
                "subject_id": subject_id,
                "impact_level": impact_result.get("impact_level", "NONE"),
                "affected_assets": impact_result.get("affected_assets", []),
                "reasoning": impact_result.get("reasoning", ""),
            }

        except Exception as e:
            print(f"ImpactAnalyzer failed for subject {subject_id}: {str(e)}")
            raise e
