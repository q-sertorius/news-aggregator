# src/news_aggregator/telegram/formatter.py

from typing import List, Dict, Any
from datetime import datetime

class ReportFormatter:
    @staticmethod
    def format_report(results: List[Dict[str, Any]], poll_time: str = None) -> str:
        """Format pipeline results into a Telegram-friendly MarkdownV2 message."""
        if not poll_time:
            poll_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            
        if not results:
            return "📰 *News Aggregator Report*\\n\\nNo new impactful news detected in this cycle\\."
        
        # Filter for impactful news (MEDIUM or HIGH)
        impactful = [r for r in results if r.get("impact") in ("MEDIUM", "HIGH")]
        
        if not impactful:
            return f"📰 *News Aggregator Report*\\n\\n{len(results)} articles processed\\. No MEDIUM/HIGH impact news detected\\."
        
        header = f"📰 *News Aggregator Report*\\n🕒 {poll_time}\\n\\n"
        header += f"_{len(impactful)} impactful update\\(s\\) detected:_\\n\\n"
        
        messages = []
        current_msg = header
        
        for i, item in enumerate(impactful, 1):
            impact_emoji = "🔴" if item["impact"] == "HIGH" else "🟡"
            
            # Escape special MarkdownV2 characters
            title = item["title"].replace(".", "\\.").replace("-", "\\-").replace("_", "\\_")
            status = item.get("status", "N/A").replace(".", "\\.").replace("-", "\\-").replace("_", "\\_")
            reasoning = item.get("reasoning", "").replace(".", "\\.").replace("-", "\\-").replace("_", "\\_")
            assets = ", ".join(item.get("assets", [])).replace("_", "\\_")
            
            entry = (
                f"{impact_emoji} *{i}\\. {title}*\\n"
                f"_Impact: {item['impact']}_\\n"
                f"Status: {status}\\n"
                f"Assets: {assets}\\n"
                f"_{reasoning}_\\n"
            )
            
            if len(current_msg) + len(entry) > 3800:  # Leave room for footer
                messages.append(current_msg)
                current_msg = entry + "\\n"
            else:
                current_msg += entry + "\\n"
        
        if current_msg.strip():
            messages.append(current_msg)
        
        # Add footer to last message
        if messages:
            footer = f"\\n\\n_Full pipeline processed {len\\(results\\)} articles\\._"
            if len(messages[-1]) + len(footer) <= 4000:
                messages[-1] += footer
            else:
                messages.append(footer)
        
        return messages[0] if len(messages) == 1 else messages

    @staticmethod
    def format_status(db_stats: Dict[str, Any]) -> str:
        """Format database statistics for /status command."""
        msg = (
            "📊 *System Status*\\n\\n"
            f"📁 Subjects tracked: {db_stats.get('subjects', 0)}\\n"
            f"📄 Articles processed: {db_stats.get('articles', 0)}\\n"
            f"⚠️ Failed articles: {db_stats.get('dead_letters', 0)}\\n"
            f"🕒 Last poll: {db_stats.get('last_poll', 'Never')}\\n"
        )
        return msg
