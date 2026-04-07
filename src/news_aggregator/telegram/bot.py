# src/news_aggregator/telegram/bot.py

import asyncio
import logging
from typing import List, Dict, Any
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError
from ..config import AppConfig
from ..db.repository import NewsRepository
from .formatter import ReportFormatter

logger = logging.getLogger(__name__)

class NewsBot:
    def __init__(self, config: AppConfig, orchestrator=None):
        self.config = config
        self.orchestrator = orchestrator
        self.repo = NewsRepository()
        self.allowed_ids = set(config.telegram_chat_ids)
        self._request = HTTPXRequest(
            connection_pool_size=8,
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=30.0,
        )
        self.app = Application.builder().token(config.telegram_bot_token).request(self._request).build()
        self._setup_handlers()
        logger.info("Telegram bot initialized. Authorized chat IDs: %s", list(self.allowed_ids))

    def _is_authorized(self, chat_id: int) -> bool:
        """Check if the chat ID is authorized."""
        return chat_id in self.allowed_ids

    def _setup_handlers(self):
        """Register command and callback handlers with authorization check."""
        self.app.add_handler(CommandHandler("start", self._auth_wrapper(self.cmd_start)))
        self.app.add_handler(CommandHandler("status", self._auth_wrapper(self.cmd_status)))
        self.app.add_handler(CommandHandler("watchlist", self._auth_wrapper(self.cmd_watchlist)))
        self.app.add_handler(CommandHandler("run", self._auth_wrapper(self.cmd_run)))
        self.app.add_handler(CallbackQueryHandler(self._auth_wrapper(self.callback_handler)))
        # Catch-all for unauthorized messages
        self.app.add_handler(MessageHandler(filters.ALL, self._auth_wrapper(self.handle_any)))

    def _auth_wrapper(self, handler):
        """Wrap handlers to check authorization before execution."""
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id if update.effective_chat else None
            if not self._is_authorized(chat_id):
                logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
                return
            return await handler(update, context)
        return wrapper

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome = (
            "📰 *Welcome to the News Aggregator\\!*\\n\\n"
            "I monitor financial and geopolitical news and deliver impact analysis\\.\\n\\n"
            "*Commands:*\\n"
            "/status \\- Show system status\\n"
            "/watchlist \\- View tracked topics\\n"
            "/run \\- Trigger a manual pipeline run\\n\\n"
            "_Reports are sent automatically every 15 minutes\\._"
        )
        await update.message.reply_text(welcome, parse_mode="MarkdownV2")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        await update.message.reply_text("Fetching status\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            stats = await self.repo.get_stats()
            msg = ReportFormatter.format_status(stats)
            await update.message.reply_text(msg, parse_mode="MarkdownV2")
        except Exception as e:
            await update.message.reply_text(f"Error fetching status: {str(e)}")

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /watchlist command."""
        topics = self.config.watchlist.topics
        if not topics:
            await update.message.reply_text("No watchlist topics configured\\.", parse_mode="MarkdownV2")
            return
        msg = "📋 *Watchlist Topics*\\n\\n"
        for t in topics:
            priority_icon = "🔴" if t.priority == 1 else "🟡" if t.priority == 2 else "🟢"
            keywords = ", ".join(t.keywords[:3])
            msg += f"{priority_icon} *{t\\.name}*\\n   _Keywords: {keywords}_\\n\\n"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")

    async def cmd_run(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /run command - trigger manual pipeline run."""
        if not self.orchestrator:
            await update.message.reply_text("Pipeline orchestrator not configured\\.", parse_mode="MarkdownV2")
            return
        await update.message.reply_text("🔄 Starting pipeline run\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            results = await self.orchestrator.run_pipeline()
            if results:
                messages = ReportFormatter.format_report(results)
                if isinstance(messages, list):
                    for msg in messages:
                        await update.message.reply_text(msg, parse_mode="MarkdownV2")
                else:
                    await update.message.reply_text(messages, parse_mode="MarkdownV2")
            else:
                await update.message.reply_text("✅ Pipeline complete\\. No impactful news found\\.", parse_mode="MarkdownV2")
        except Exception as e:
            await update.message.reply_text(f"❌ Pipeline error: {str(e)}")

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks."""
        query = update.callback_query
        await query.answer()
        if query.data.startswith("detail:"):
            subject_id = query.data.split(":")[1]
            await query.edit_message_text(f"Details for subject {subject_id} \\- coming soon\\.", parse_mode="MarkdownV2")

    async def handle_any(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Silently ignore non-command messages from authorized users."""
        pass

    async def send_report(self, results: List[Dict[str, Any]]):
        """Push a report to all configured chat IDs with retry on timeout."""
        if not results:
            return
        messages = ReportFormatter.format_report(results)
        if isinstance(messages, str):
            messages = [messages]
        for chat_id in self.config.telegram_chat_ids:
            for msg in messages:
                await self._send_with_retry(chat_id, msg)

    async def _send_with_retry(self, chat_id: int, text: str, max_retries: int = 3):
        """Send a message with exponential backoff retry on network errors."""
        for attempt in range(max_retries):
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="MarkdownV2",
                )
                return  # Success
            except (TimedOut, NetworkError) as e:
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning(f"Telegram send failed (attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            except Exception as e:
                logger.error(f"Failed to send report to {chat_id}: {e}")
                return  # Non-retryable error, give up
        logger.error(f"Failed to send report to {chat_id} after {max_retries} retries")
                return  # Non-retryable error, give up
        logger.error(f"Failed to send report to {chat_id} after {max_retries} retries")

    def run(self):
        """Start the bot with automatic restart on network failure."""
        logger.info("Starting Telegram Bot...")
        self.app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            retry_after=60,  # Auto-reconnect after 60s on network errors
            timeout=30,
        )
