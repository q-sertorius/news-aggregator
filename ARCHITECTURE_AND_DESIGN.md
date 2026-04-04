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
    [Telegram Bot / Scheduler] --> [Formatted Status Report] --> [User Telegram]

## 2. Component Breakdown
### 2.1 Scheduler & Orchestrator
- **Technology**: `APScheduler` (Async) integrated with `python-telegram-bot` (v20+).
- **Role**: Triggers the 15-minute pipeline, manages concurrency, handles graceful shutdowns, and ensures non-blocking execution.

### 2.2 News Fetcher & Pre-Filter
- **Technology**: `feedparser`, `aiohttp`.
- **Role**: Polls configured RSS feeds, parses XML, applies keyword/category filters to exclude irrelevant domains (sports, entertainment), and deduplicates headlines.

### 2.3 Agent Pipeline (Sequential with Shared State)
- **Base Agent Class**: Abstract interface for `run(input_data) -> output_data`.
- **Facts Summarizer**: Calls OpenRouter API with strict system prompt enforcing factual extraction. Handles token limits by chunking long articles.
- **Context Tracker**: Queries SQLite for existing subjects. Uses lightweight LLM call or rule-based matching to map new facts to subjects. Updates DB state.
- **Investment Analyzer**: Evaluates mapped subjects against market impact criteria. Outputs structured JSON with impact scores and affected assets.

### 2.4 Telegram Interface
- **Technology**: `python-telegram-bot` (PTB).
- **Role**: Receives processed pipeline output, formats it into Telegram-compatible MarkdownV2, handles user commands, and manages chat IDs securely.

### 2.5 Data Layer (SQLite)
- **Schema**:
  - `subjects`: `id`, `name`, `category`, `watchlist_flag`, `created_at`
  - `articles`: `id`, `subject_id`, `title`, `source_url`, `fetched_at`
  - `history`: `id`, `subject_id`, `status_snapshot`, `impact_level`, `updated_at`
- **Access**: `aiosqlite` for async compatibility with PTB and APScheduler.

## 3. Data Flow (15-Minute Cycle)
1. **Trigger**: Scheduler fires `run_pipeline()`.
2. **Fetch**: `Fetcher` pulls RSS, filters noise, returns list of `Article` objects.
3. **Summarize**: `FactsAgent` processes each article in parallel (batched to respect rate limits), returns `FactSummary`.
4. **Contextualize**: `ContextAgent` matches summaries to DB subjects. Creates new subjects if unmatched. Updates `history` table.
5. **Analyze**: `ImpactAgent` evaluates updated subjects, assigns market impact tags.
6. **Format & Send**: Orchestrator compiles final report. PTB sends message to configured chat.
7. **Log & Cleanup**: Pipeline logs metrics, prunes old DB records if retention limit reached.

## 4. Tech Stack
- **Language**: Python 3.10+
- **LLM Gateway**: OpenRouter API (`qwen/qwen3.6-plus:free`) via `openai` Python SDK (compatible endpoint)
- **Scheduling**: `APScheduler` (AsyncIO)
- **Messaging**: `python-telegram-bot` (v20+)
- **Database**: `aiosqlite`
- **Parsing**: `feedparser`, `beautifulsoup4` (for fallback content extraction)
- **Config**: `pydantic-settings` + `.env`

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
