# src/news_aggregator/web/server.py

import asyncio
import json
import logging
from aiohttp import web
from ..db.repository import NewsRepository
from ..db.vector_store import VectorStore
from ..pipeline.orchestrator import PipelineOrchestrator
from ..config import AppConfig

logger = logging.getLogger(__name__)


class WebDashboard:
    def __init__(
        self,
        orchestrator: PipelineOrchestrator,
        repo: NewsRepository,
        vstore: VectorStore,
    ):
        self.orchestrator = orchestrator
        self.repo = repo
        self.vstore = vstore
        self.app = web.Application()
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/api/status", self.api_status)
        self.app.router.add_get("/api/subjects", self.api_subjects)
        self.app.router.add_get("/api/articles", self.api_articles)
        self.app.router.add_get("/api/dead_letters", self.api_dead_letters)
        self.app.router.add_post("/api/run", self.api_run)
        # Serve static files and templates
        self.app.router.add_static("/static/", path="src/news_aggregator/web/static/")

    async def index(self, request: web.Request) -> web.Response:
        with open("src/news_aggregator/web/templates/index.html", "r") as f:
            html = f.read()
        return web.Response(text=html, content_type="text/html")

    async def api_status(self, request: web.Request) -> web.Response:
        try:
            stats = await self.repo.get_stats()
            return web.json_response(stats)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_subjects(self, request: web.Request) -> web.Response:
        try:
            subjects = await self.repo.get_active_subjects(limit=50)
            return web.json_response(subjects)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_articles(self, request: web.Request) -> web.Response:
        try:
            articles = await self.repo.get_recent_articles(limit=20)
            return web.json_response(articles)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_dead_letters(self, request: web.Request) -> web.Response:
        try:
            items = await self.repo.get_dead_letters(limit=20)
            return web.json_response(items)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_run(self, request: web.Request) -> web.Response:
        """Trigger a manual pipeline run."""
        try:
            results = await self.orchestrator.run_pipeline()
            return web.json_response(
                {"success": True, "count": len(results), "results": results}
            )
        except Exception as e:
            logger.error(f"Pipeline run failed: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    def run(self, host: str = "127.0.0.1", port: int = 8080):
        logger.info(f"Starting web dashboard at http://{host}:{port}")
        web.run_app(self.app, host=host, port=port)
