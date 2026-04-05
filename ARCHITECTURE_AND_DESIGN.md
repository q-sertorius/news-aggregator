# Architecture & Design Document

## 1. High-Level Architecture

    [RSS Feeds] --> (Fetcher & Filter) --> [Raw Articles]
                                          |
                                          v
    [Facts Summarizer Agent] <-- LLM (OpenRouter) --> [Fact-Only Summaries]
                                          |
                                          v
    [Context Tracker Agent] <--> [SQLite DB] --> [Subject Status & History]
                                          |
                                          v
    [Investment Impact Agent] <-- LLM (OpenRouter) --> [Impact Analysis]
                                          |
                                          v
    [Telegram Bot / Scheduler] --> [Formatted Status Report + Source Links] --> [User Telegram]
                                          ^
                                          |
    [Topic Curator Agent] (Async/Daily) --> [Dynamic Watchlist & Pruning]

## 2. Component Breakdown
### 2.1 Scheduler & Orchestrator
- **Technology**: `APScheduler` (Async) integrated with `python-telegram-bot` (v20+).
- **Role**: Triggers the configurable polling pipeline (default 15-min), manages concurrency, handles graceful shutdowns, and ensures non-blocking execution. Schedules slower background jobs (e.g., Topic Curation, DB cleanup).

### 2.2 News Fetcher & Pre-Filter
- **Technology**: `feedparser`, `aiohttp`.
- **Role**: Polls configured RSS feeds, parses XML, applies keyword/category filters to exclude irrelevant domains (sports, entertainment), and deduplicates headlines. Preserves `source_url`, `published_at`, and `author` metadata for downstream use.

### 2.3 Agent Pipeline (Sequential with Shared State)
- **Base Agent Class**: Abstract interface for `run(input_data) -> output_data`.
- **Facts Summarizer**: Calls OpenRouter API with strict system prompt enforcing factual extraction. Handles token limits by chunking long articles. Passes through original `source_url` and `title`.
- **Context Tracker**: Queries SQLite for existing subjects. Uses lightweight LLM call or rule-based matching to map new facts to subjects. Updates DB state.
- **Investment Analyzer**: Evaluates mapped subjects against market impact criteria. Outputs structured JSON with impact scores and affected assets.

### 2.4 Topic Curator & Watchlist Manager (New)
- **Technology**: LLM (OpenRouter) + Rule-based heuristics.
- **Role**: Runs on a slower schedule (e.g., daily or weekly). Reviews tracked subjects for relevance, prunes stale/low-impact topics, identifies emerging macro trends, and dynamically updates the active watchlist. Reduces manual maintenance and keeps the pipeline focused.

### 2.5 Telegram Interface
- **Technology**: `python-telegram-bot` (PTB).
- **Role**: Receives processed pipeline output, formats it into Telegram-compatible MarkdownV2, handles user commands, and manages chat IDs securely.
- **Interactive Features**: 
  - Embeds direct hyperlinks to original articles in the report.
  - Generates `InlineKeyboardButton` elements for quick actions: `🔗 Read Source`, `📖 Full Context`, `📊 Impact Details`.
  - Handles callback queries to fetch and display extended subject history or full article text on demand.

### 2.6 Data Layer (SQLite)
- **Schema**:
  - `subjects`: `id`, `name`, `category`, `watchlist_flag`, `created_at`, `last_seen`, `relevance_score`
  - `articles`: `id`, `subject_id`, `title`, `source_url`, `published_at`, `fetched_at`, `summary_snippet`
  - `history`: `id`, `subject_id`, `status_snapshot`, `impact_level`, `updated_at`
  - `watchlist`: `id`, `topic_name`, `keywords`, `priority`, `is_active`
- **Access**: `aiosqlite` for async compatibility with PTB and APScheduler.

## 3. Data Flow (Configurable Cycle)
1. **Trigger**: Scheduler fires `run_pipeline()` at configured interval (default: 15 min).
2. **Fetch**: `Fetcher` pulls RSS, filters noise, returns list of `Article` objects (preserving URLs & metadata).
3. **Summarize**: `FactsAgent` processes each article in parallel (batched to respect rate limits), returns `FactSummary` with attached `source_url`.
4. **Contextualize**: `ContextAgent` matches summaries to DB subjects. Creates new subjects if unmatched. Updates `history` table.
5. **Analyze**: `ImpactAgent` evaluates updated subjects, assigns market impact tags.
6. **Format & Send**: Orchestrator compiles final report. PTB formats MarkdownV2 with embedded hyperlinks and inline buttons. Sends to configured chat.
7. **Log & Cleanup**: Pipeline logs metrics, prunes old DB records if retention limit reached.
8. **Curate (Async)**: `TopicCurator` periodically reviews subject relevance, updates watchlist, and archives inactive topics.

## 4. Tech Stack
- **Language**: Python 3.10+
- **LLM Gateway**: OpenRouter API (`qwen/qwen3.6-plus:free`) via `openai` Python SDK (compatible endpoint)
- **Scheduling**: `APScheduler` (AsyncIO)
- **Messaging**: `python-telegram-bot` (v20+)
- **Database**: `aiosqlite`
- **Parsing**: `feedparser`, `beautifulsoup4` (for fallback content extraction)
- **Config**: `pydantic-settings` + `.env` + `config.yaml` (for complex lists like RSS feeds & watchlist)

## 5. Error Handling & Resilience
- **LLM Failures**: Retry up to 3 times with exponential backoff. Fallback to cached summary or skip with warning.
- **RSS Downtime**: Skip failed sources, log error, continue with remaining feeds.
- **Rate Limits**: Implement token bucket or sliding window rate limiter for OpenRouter calls.
- **State Consistency**: Use SQLite transactions for DB updates. Rollback on pipeline failure.
- **Monitoring**: Console logging with structured JSON output for easy debugging. Optional health-check endpoint.

## 6. Security & Configuration
- All secrets (`OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) loaded via `python-dotenv`.
- No hardcoded credentials.
- Input sanitization on all LLM prompts to prevent injection.
- Telegram bot restricted to specific chat ID(s) for security.
- **Highly Configurable**: Polling intervals, RSS sources, LLM parameters, impact thresholds, and retention policies are externalized to `.env` and `config.yaml`.
