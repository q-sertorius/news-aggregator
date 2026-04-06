# Detailed Design Document: Agentic News Aggregator

## 1. Project Structure

```
news_aggregator/
├── .env                          # Secrets (API keys, tokens)
├── config.yaml                   # RSS feeds, watchlist, thresholds
├── pyproject.toml                # Dependencies & build config
├── src/
│   └── news_aggregator/
│       ├── __init__.py
│       ├── main.py               # Entry point, bootstrap
│       ├── config.py             # Pydantic settings loader
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py         # SQLAlchemy/aiosqlite table definitions
│       │   ├── repository.py     # CRUD operations
│       │   └── migrations.py     # Schema init & migrations
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py           # Abstract Agent interface
│       │   ├── facts_summarizer.py
│       │   ├── context_tracker.py
│       │   ├── impact_analyzer.py
│       │   └── topic_curator.py
│       ├── fetcher/
│       │   ├── __init__.py
│       │   ├── rss_fetcher.py    # feedparser + aiohttp
│       │   └── deduplicator.py   # Headline dedup logic
│       ├── telegram/
│       │   ├── __init__.py
│       │   ├── bot.py            # Bot initialization
│       │   ├── commands.py       # /start, /status, /watchlist, etc.
│       │   ├── callbacks.py      # Inline button handlers
│       │   └── formatter.py      # MarkdownV2 report builder
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── orchestrator.py   # run_pipeline() coordinator
│       │   └── rate_limiter.py   # Token bucket for LLM calls
│       └── utils/
│           ├── __init__.py
│           ├── logging.py        # Structured JSON logger
│           └── prompts.py        # LLM system prompt templates
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_fetcher.py
│   ├── test_agents.py
│   ├── test_pipeline.py
│   ├── test_telegram.py
│   └── test_db.py
└── AGENTS.md
```

## 2. Database Schema (SQLite via aiosqlite)

### 2.1 `subjects`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique subject ID |
| `name` | TEXT | NOT NULL, UNIQUE | Normalized subject name (e.g., "Fed Interest Rates") |
| `category` | TEXT | NOT NULL | One of: geopolitics, macroeconomics, central_banks, corporate, tech_supply_chain, commodities, forex, crypto |
| `watchlist_flag` | BOOLEAN | DEFAULT 0 | 1 = on predefined watchlist, 0 = dynamically detected |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | First time subject was seen |
| `last_seen` | TIMESTAMP | NOT NULL | Most recent article timestamp |
| `latest_status` | TEXT | | Current status summary (updated each cycle) |
| `impact_level` | TEXT | DEFAULT 'NONE' | HIGH, MEDIUM, LOW, NONE |
| `relevance_score` | REAL | DEFAULT 0.5 | 0.0–1.0, decays over time if no updates |
| `affected_assets` | TEXT | | JSON array of affected tickers/sectors |

### 2.2 `articles`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique article ID |
| `subject_id` | INTEGER | NOT NULL, FK → subjects.id | Linked subject |
| `title` | TEXT | NOT NULL | Original headline |
| `source_url` | TEXT | NOT NULL, UNIQUE | Canonical URL (dedup key) |
| `published_at` | TIMESTAMP | | Article publish date from RSS |
| `fetched_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When system fetched it |
| `feed_name` | TEXT | | Source feed identifier |
| `author` | TEXT | | Article author if available |
| `summary_snippet` | TEXT | | Facts summarizer output (truncated) |
| `raw_content` | TEXT | | Full article text (optional, for fallback) |

### 2.3 `subject_history`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | History entry ID |
| `subject_id` | INTEGER | NOT NULL, FK → subjects.id | Linked subject |
| `status_snapshot` | TEXT | NOT NULL | Status text at this point in time |
| `impact_level` | TEXT | | Impact level at this snapshot |
| `article_ids` | TEXT | | JSON array of contributing article IDs |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When snapshot was created |

### 2.4 `watchlist`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Watchlist entry ID |
| `topic_name` | TEXT | NOT NULL, UNIQUE | Human-readable topic name |
| `keywords` | TEXT | NOT NULL | JSON array of trigger keywords/phrases |
| `priority` | INTEGER | DEFAULT 1 | 1 = highest, 3 = lowest |
| `is_active` | BOOLEAN | DEFAULT 1 | 0 = archived by curator |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | |
| `last_reviewed` | TIMESTAMP | | Last curator review timestamp |

### 2.5 Indexes
```sql
CREATE INDEX idx_articles_subject ON articles(subject_id);
CREATE INDEX idx_articles_fetched ON articles(fetched_at);
CREATE INDEX idx_history_subject ON subject_history(subject_id);
CREATE INDEX idx_subjects_last_seen ON subjects(last_seen);
CREATE INDEX idx_watchlist_active ON watchlist(is_active);
```

## 3. Configuration Schema

### 3.1 `.env` (secrets)
```
OPENROUTER_API_KEY=sk-or-...
TELEGRAM_BOT_TOKEN=123456:ABC-...
TELEGRAM_CHAT_IDS=111222333,444555666
```

### 3.2 `config.yaml`
```yaml
polling:
  interval_minutes: 15
  max_pipeline_duration_minutes: 5

feeds:
  # Macroeconomics & Central Banks
  - url: "https://www.reuters.com/finance/economy/"
    category: "macroeconomics"
  - url: "https://feeds.bloomberg.com/markets/news.rss"
    category: "macroeconomics"
  - url: "https://www.ft.com/markets?format=rss"
    category: "macroeconomics"
  - url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"
    category: "macroeconomics"

  # Geopolitics & World News
  - url: "https://feeds.reuters.com/reuters/worldNews"
    category: "geopolitics"
  - url: "https://feeds.bbci.co.uk/news/world/rss.xml"
    category: "geopolitics"
  - url: "https://www.aljazeera.com/xml/rss/all.xml"
    category: "geopolitics"
  - url: "https://rsshub.app/apnews/topics/world-news"
    category: "geopolitics"

  # Tech & Supply Chain
  - url: "https://www.reuters.com/technology/rss"
    category: "tech_supply_chain"
  - url: "https://techcrunch.com/feed/"
    category: "tech_supply_chain"
  - url: "https://www.theverge.com/rss/index.xml"
    category: "tech_supply_chain"

  # Commodities & Energy
  - url: "https://oilprice.com/rss/main"
    category: "commodities"
  - url: "https://www.mining.com/feed/"
    category: "commodities"

  # Crypto & Digital Assets
  - url: "https://www.coindesk.com/arc/outboundfeeds/rss/"
    category: "crypto"
  - url: "https://www.theblock.co/rss.xml"
    category: "crypto"

  # Corporate & Markets
  - url: "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
    category: "corporate"
  - url: "https://www.ft.com/companies?format=rss"
    category: "corporate"
  - url: "https://feeds.bbci.co.uk/news/world/rss.xml"
    category: "geopolitics"
  - url: "https://www.aljazeera.com/xml/rss/all.xml"
    category: "geopolitics"
  - url: "https://rsshub.app/apnews/topics/world-news"
    category: "geopolitics"

  # Tech & Supply Chain
  - url: "https://www.reuters.com/technology/rss"
    category: "tech_supply_chain"
  - url: "https://techcrunch.com/feed/"
    category: "tech_supply_chain"
  - url: "https://www.theverge.com/rss/index.xml"
    category: "tech_supply_chain"

  # Commodities & Energy
  - url: "https://oilprice.com/rss/main"
    category: "commodities"
  - url: "https://www.mining.com/feed/"
    category: "commodities"

  # Crypto & Digital Assets
  - url: "https://www.coindesk.com/arc/outboundfeeds/rss/"
    category: "crypto"
  - url: "https://www.theblock.co/rss.xml"
    category: "crypto"

  # Corporate & Markets
  - url: "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
    category: "corporate"
  - url: "https://www.ft.com/companies?format=rss"
    category: "corporate"

llm:
  model: "qwen/qwen3.6-plus:free"
  base_url: "https://openrouter.ai/api/v1"
  max_tokens: 2000
  temperature: 0.1
  rate_limit_rpm: 10

impact:
  weights:
    equities: 1.0
    forex: 0.8
    bonds: 0.6
    commodities: 0.7
  thresholds:
    high: 0.8
    medium: 0.5
    low: 0.2

retention:
  db_retention_days: 30
  max_articles_per_subject: 50

telegram:
  report_format: "markdownv2"
  enable_inline_buttons: true
  notification_threshold: "MEDIUM"
  max_message_length: 4000

watchlist:
  topics:
    - name: "Fed Interest Rates"
      keywords: ["federal reserve", "interest rate", "fomc", "jerome powell"]
      priority: 1
    - name: "US-China Trade"
      keywords: ["china trade", "tariffs", "semiconductor export"]
      priority: 1
    - name: "NVIDIA/AI Chips"
      keywords: ["nvidia", "ai chips", "gpu shortage", "semiconductor"]
      priority: 2
    - name: "Oil Prices"
      keywords: ["oil price", "crude", "opec", "brent"]
      priority: 2
```

### 3.3 Config Classes (Pydantic)
```python
class PollingConfig(BaseModel):
    interval_minutes: int = 15
    max_pipeline_duration_minutes: int = 5

class FeedConfig(BaseModel):
    url: str
    category: str

class LLMConfig(BaseModel):
    model: str = "qwen/qwen3.6-plus:free"
    base_url: str = "https://openrouter.ai/api/v1"
    max_tokens: int = 2000
    temperature: float = 0.1
    rate_limit_rpm: int = 10

class ImpactConfig(BaseModel):
    weights: dict[str, float]
    thresholds: dict[str, float]

class RetentionConfig(BaseModel):
    db_retention_days: int = 30
    max_articles_per_subject: int = 50

class TelegramConfig(BaseModel):
    report_format: str = "markdownv2"
    enable_inline_buttons: bool = True
    notification_threshold: str = "MEDIUM"
    max_message_length: int = 4000

class WatchlistTopic(BaseModel):
    name: str
    keywords: list[str]
    priority: int = 1

class WatchlistConfig(BaseModel):
    topics: list[WatchlistTopic]

class AppConfig(BaseSettings):
    openrouter_api_key: str
    telegram_bot_token: str
    telegram_chat_ids: list[int]
    polling: PollingConfig
    feeds: list[FeedConfig]
    llm: LLMConfig
    impact: ImpactConfig
    retention: RetentionConfig
    telegram: TelegramConfig
    watchlist: WatchlistConfig

    model_config = SettingsConfigDict(
        env_file=".env",
        yaml_file="config.yaml",
    )
```

## 4. Agent Interface & Implementations

### 4.1 Abstract Base
```python
class BaseAgent(ABC):
    def __init__(self, llm_client: AsyncOpenAI, config: AppConfig):
        self.llm = llm_client
        self.config = config

    @abstractmethod
    async def run(self, input_data: Any) -> Any:
        ...

    async def _call_llm(self, system_prompt: str, user_prompt: str,
                        response_format: dict | None = None) -> str:
        # Handles rate limiting, retries (3x exponential backoff),
        # token truncation, and error fallback
        ...
```

### 4.2 FactsSummarizer
- **Input**: `Article(title, raw_content, source_url, published_at, feed_name, author)`
- **Output**: `FactSummary(title, facts: list[str], source_url, published_at, numbers: list[str])`
- **Prompt strategy**: System prompt enforces "ONLY verifiable facts, no opinions." Response parsed as JSON array of fact strings.
- **Chunking**: If article > 4000 tokens, split by paragraphs, summarize each chunk, then merge.

### 4.3 ContextTracker
- **Input**: `list[FactSummary]`
- **Output**: `list[TrackedSubject(subject_id, classification: NEW_SUBJECT|ONGOING_DEVELOPMENT, updated_status)]`
- **Matching**: Two-phase:
  1. Keyword overlap with watchlist topics (fast path)
  2. LLM-based semantic matching for uncategorized facts (fallback)
- **DB operations**: Inserts new subjects, updates `latest_status`, appends to `subject_history`.

### 4.4 ImpactAnalyzer
- **Input**: `list[TrackedSubject]`
- **Output**: `list[ImpactResult(subject_id, impact_level: HIGH|MEDIUM|LOW|NONE, affected_assets: list[str], reasoning: str)]`
- **Scoring**: LLM evaluates against impact criteria, then numeric score mapped to thresholds from config.
- **Response format**: JSON with `impact_level`, `affected_assets`, `reasoning`.

### 4.5 TopicCurator
- **Input**: All subjects from DB, current watchlist
- **Output**: `CuratorReport(pruned_ids: list[int], new_topics: list[WatchlistTopic], archive_count: int)`
- **Schedule**: Runs daily via separate APScheduler job.
- **Logic**:
  - Prune subjects with `last_seen` > retention_days and `impact_level` = NONE
  - Identify clusters of new subjects that suggest emerging trends
  - Update `relevance_score` based on recency and impact
  - Archive low-priority inactive watchlist entries

## 5. LLM Prompt Templates

### 5.1 Facts Summarizer
```
System: You are a financial news facts extractor. Extract ONLY verifiable facts, figures, dates, and direct statements from the article. Zero tolerance for opinions, speculation, editorializing, or emotional language. Output MUST be a JSON object with keys: "facts" (array of strings), "numbers" (array of key figures), "entities" (array of mentioned organizations/people).

User: Article Title: {title}
Published: {published_at}
Content: {content}

Return JSON only.
```

### 5.2 Context Tracker
```
System: You are a news topic classifier. Given a list of known subjects and new fact summaries, match each fact to the most relevant subject or flag it as NEW_SUBJECT. Output MUST be a JSON array of objects with keys: "fact_index", "subject_id" (or null if new), "classification" ("NEW_SUBJECT" or "ONGOING_DEVELOPMENT"), "suggested_name" (if new), "status_update" (one-line status).

Known Subjects:
{subjects_json}

Fact Summaries:
{facts_json}

Return JSON array only.
```

### 5.3 Impact Analyzer
```
System: You are an investment impact analyst. Evaluate each news subject for potential impact on financial markets (equities primary, then forex, bonds, commodities). Output MUST be a JSON array of objects with keys: "subject_id", "impact_level" ("HIGH", "MEDIUM", "LOW", "NONE"), "affected_assets" (array of tickers/sectors), "reasoning" (one sentence).

Subjects:
{subjects_json}

Return JSON array only.
```

### 5.4 Topic Curator
```
System: You are a topic curator. Review tracked subjects and the current watchlist. Identify stale topics to prune, emerging trends to add, and relevance score adjustments. Output MUST be JSON with keys: "prune_subject_ids" (array of ints), "emerging_topics" (array of {name, keywords}), "relevance_updates" (array of {subject_id, new_score}).

Subjects (last 30 days):
{subjects_json}

Current Watchlist:
{watchlist_json}

Return JSON only.
```

## 6. Telegram Interface

### 6.1 Commands
| Command | Handler | Description |
|---|---|---|
| `/start` | `cmd_start` | Welcome message, registers chat ID, shows `/help` |
| `/status` | `cmd_status` | Sends current status report for all active subjects |
| `/watchlist` | `cmd_watchlist` | Lists active watchlist topics with priority |
| `/help` | `cmd_help` | Shows available commands and usage |
| `/config` | `cmd_config` | Shows current configuration summary (read-only) |
| `/details <subject_id>` | `cmd_details` | Retrieves full history + linked sources for a subject |

### 6.2 Inline Keyboard Buttons (per report item)
```
[🔗 Read Source]  [📖 Full Context]  [📊 Impact Details]
```
- `Read Source` → Opens `source_url` directly
- `Full Context` → Callback `ctx:{subject_id}` → fetches `subject_history`, formats timeline
- `Impact Details` → Callback `imp:{subject_id}` → fetches impact analysis, affected assets

### 6.3 Callback Query Routing
```python
CALLBACK_PREFIXES = {
    "ctx:": handle_context_callback,
    "imp:": handle_impact_callback,
    "src:": handle_source_callback,
}
```

### 6.4 Report Formatter
```python
class ReportFormatter:
    def format_report(self, pipeline_output: PipelineResult) -> str:
        # Groups by impact level (HIGH first)
        # Marks new developments with "⚡ UPDATE:" or "🔴 NEW:"
        # Truncates to max_message_length, splits into multiple messages if needed
        # Escapes MarkdownV2 special characters

    def build_inline_keyboard(self, subject_id: int, source_url: str) -> InlineKeyboardMarkup:
        # Returns keyboard with Read Source, Full Context, Impact Details buttons
```

## 7. Pipeline Orchestrator

### 7.1 `run_pipeline()` Flow
```
1. Record start time
2. Fetcher.poll() → list[Article]
3. Deduplicator.deduplicate(articles) → list[Article] (filter by source_url hash)
4. If no new articles → log and return early
5. FactsSummarizer.run(articles) → list[FactSummary] (parallel, batched by rate limiter)
6. ContextTracker.run(fact_summaries) → list[TrackedSubject]
7. ImpactAnalyzer.run(tracked_subjects) → list[ImpactResult]
8. ReportFormatter.format(impact_results) → str
9. TelegramBot.send_report(formatted_report)
10. Log metrics (articles processed, LLM calls, duration)
11. Check retention → prune old records if needed
```

### 7.2 Concurrency Model
- Fetcher: sequential per feed (to respect individual feed rate limits)
- Facts Summarizer: parallel via `asyncio.gather()`, bounded by semaphore (max 3 concurrent LLM calls)
- Context Tracker + Impact Analyzer: sequential (DB writes must be ordered)
- Telegram send: sequential

### 7.3 Rate Limiter
```python
class RateLimiter:
    def __init__(self, rpm: int):
        self.semaphore = asyncio.Semaphore(rpm)
        self.window = 60  # seconds

    async def acquire(self):
        async with self.semaphore:
            yield
```

## 8. Error Handling & Resilience

| Failure Mode | Strategy |
|---|---|
| RSS feed unreachable | Log warning, skip feed, continue with remaining |
| LLM API timeout | Retry 3x with exponential backoff (1s, 2s, 4s). If all fail, use cached summary or skip article with warning |
| LLM rate limit (429) | Wait for retry-after header, then resume |
| LLM malformed response | Retry with stricter prompt. If still fails, skip and log |
| SQLite write failure | Rollback transaction, log error, retry pipeline step once |
| Telegram send failure | Retry 2x. If persistent, log and queue for next cycle |
| Pipeline exceeds max duration | Abort remaining steps, send partial report with warning |

## 9. Logging

Structured JSON logging via Python's `logging` module:
```json
{"level": "INFO", "timestamp": "2026-04-06T10:00:00Z", "module": "pipeline", "event": "pipeline_complete", "articles_processed": 12, "llm_calls": 15, "duration_seconds": 45}
```

Log levels:
- `DEBUG`: Raw API requests/responses, DB queries
- `INFO`: Pipeline milestones, article counts, report sent
- `WARNING`: Skipped feeds, retry attempts, rate limit hits
- `ERROR`: Unrecoverable failures, DB corruption, bot crashes

## 10. Testing Strategy

### 10.1 Unit Tests
- `test_fetcher.py`: Mock RSS XML responses, verify parsing and filtering
- `test_agents.py`: Mock LLM responses, verify agent input/output contracts
- `test_deduplicator.py`: Test exact and fuzzy headline matching
- `test_formatter.py`: Verify MarkdownV2 escaping and length splitting

### 10.2 Integration Tests
- `test_pipeline.py`: Full pipeline with mocked LLM and DB (in-memory SQLite)
- `test_db.py`: Schema creation, CRUD operations, retention pruning

### 10.3 Test Fixtures
- Sample RSS feeds (XML files)
- Mock LLM responses (JSON fixtures for each agent)
- Pre-populated SQLite test databases

### 10.4 Test Commands
```bash
pytest tests/                          # All tests
pytest tests/ -m unit                  # Unit only
pytest tests/ --cov=src                # Coverage report
```

## 11. Deployment & Operations

### 11.1 Local Development
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # Fill in secrets
cp config.example.yaml config.yaml  # Adjust feeds/watchlist
python -m src.news_aggregator.main
```

### 11.2 Production (Docker)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
COPY config.yaml .
CMD ["python", "-m", "src.news_aggregator.main"]
```

### 11.3 Health Checks
- Console log heartbeat every polling cycle
- Optional: HTTP health endpoint on `localhost:8080/health` returning `{"status": "ok", "last_run": "..."}`
