# Functional Requirement Specification: Agentic News Aggregator & Summarizer

## 1. System Overview
An automated, agent-driven news monitoring system that polls RSS feeds on a configurable schedule, filters for market-relevant content, summarizes facts strictly, tracks subject evolution, analyzes investment impact, and delivers structured status updates via Telegram.

## 2. Data Ingestion & Filtering
- **Sources**: RSS feeds from reputable financial, geopolitical, and macroeconomic news outlets. Fully configurable via `config.yaml`.
- **Polling Interval**: Configurable (default: 15 minutes). Adjustable via environment variables or config file.
- **Filtering Rules**:
  - Include: Geopolitics, Macroeconomics, Central Banks, Corporate Earnings, Tech/Supply Chain, Commodities, Forex, Crypto.
  - Exclude: Sports, Entertainment, Lifestyle, Celebrity News, Pure Opinion/Editorials.
  - Deduplication: Remove exact or near-duplicate headlines across sources before processing.
- **Metadata Preservation**: `source_url`, `published_at`, `author`, and `feed_name` are extracted and passed through the entire pipeline for traceability.

## 3. Agent Specifications
### 3.1 Facts & Numbers Summarizer Agent
- **Input**: Raw article text/metadata.
- **Task**: Extract and summarize ONLY verifiable facts, figures, dates, and direct statements.
- **Constraints**: Zero tolerance for opinions, speculation, editorializing, or emotional language. Output must be objective and concise.

### 3.2 Context & History Tracker Agent
- **Input**: Summarized facts + SQLite history database.
- **Task**: Compare current facts against historical records for each subject.
- **Output**: Classify each item as `NEW_SUBJECT` or `ONGOING_DEVELOPMENT`. If ongoing, append the new development to the existing timeline/status.

### 3.3 Investment Impact Analyzer Agent
- **Input**: Context-tracked subjects.
- **Task**: Evaluate potential impact on financial markets, with a primary focus on equities (stocks), secondary focus on forex, bonds, and commodities.
- **Output**: Assign impact level (`HIGH`, `MEDIUM`, `LOW`, `NONE`) and identify affected sectors/assets.

### 3.4 Topic Curator & Watchlist Manager Agent (New)
- **Input**: Historical subject data, current watchlist, trending keywords.
- **Task**: Periodically evaluate tracked subjects for continued relevance. Prune stale/low-impact topics. Identify emerging macro trends and suggest additions to the active watchlist.
- **Schedule**: Runs asynchronously (e.g., daily or weekly), decoupled from the main 15-minute polling cycle.
- **Output**: Updated `watchlist` table, archived subjects, and optional Telegram notification for major watchlist changes.

## 4. Subject Tracking & Clustering
- **Hybrid Approach**:
  - **Predefined Watchlist**: Core subjects tracked explicitly (e.g., "Fed Interest Rates", "US-China Trade", "NVIDIA/AI Chips", "Oil Prices"). Configurable via `config.yaml`.
  - **Dynamic Detection**: LLM automatically identifies and names emerging topics not on the watchlist, adding them to the tracking pool if they meet relevance thresholds.
- **State Management**: Each subject maintains a `latest_status`, `last_updated`, `impact_level`, `relevance_score`, and `development_history`.

## 5. Output & Delivery
- **Platform**: Telegram Bot.
- **Trigger**: Every polling cycle after processing completes.
- **Format**: Structured status report.
  - Unchanged subjects: Display current status concisely.
  - New developments: Highlight with clear markers (e.g., `🔴 NEW DEVELOPMENT:` or `⚡ UPDATE:`).
  - Grouped by impact level or sector for readability.
- **Source Linking & Interactivity**:
  - Every reported item includes a direct MarkdownV2 hyperlink to the original article (`[Title](URL)`).
  - Inline keyboard buttons attached to each message: `🔗 Read Source`, `📖 Full Context`, `📊 Impact Details`.
  - Callback handlers fetch and reply with extended timelines, related articles, or full impact breakdowns without cluttering the main feed.
- **Commands**: `/start`, `/status`, `/watchlist`, `/help`, `/config`, `/details <subject_id>` (retrieves complete history & all linked sources for a topic).

## 6. Data Storage
- **Database**: SQLite.
- **Tables**: `subjects`, `articles`, `subject_history`, `watchlist`.
- **Retention**: Configurable (default: 30 days) to manage DB size and context window limits. Auto-pruning handled by scheduler.
- **Traceability**: `articles` table retains `source_url`, `published_at`, and `summary_snippet` to support on-demand detail retrieval and source verification.

## 7. Configuration & Customization
- **Polling**: `POLLING_INTERVAL_MINUTES` (default: 15)
- **Feeds**: `RSS_FEEDS` (list of URLs with optional category tags)
- **LLM**: `LLM_MODEL`, `MAX_TOKENS`, `TEMPERATURE`, `RATE_LIMIT_RPM`
- **Impact Scoring**: Customizable weights for equities, forex, commodities, etc.
- **Retention**: `DB_RETENTION_DAYS` (default: 30)
- **Telegram**: `TELEGRAM_CHAT_IDS`, `REPORT_FORMAT`, `NOTIFICATION_THRESHOLDS`, `ENABLE_INLINE_BUTTONS`
- All settings managed via `.env` (secrets) and `config.yaml` (structured lists/objects).

## 8. Non-Functional Requirements
- **Reliability**: Graceful handling of RSS feed failures, API rate limits, and LLM timeouts. Retry logic with exponential backoff.
- **Cost Efficiency**: Optimized for OpenRouter free tier (`qwen/qwen3.6-plus:free`). Token usage minimized via strict prompt engineering and context truncation.
- **Latency**: Full pipeline (fetch → process → send) must complete within 5 minutes to allow buffer before next poll.
- **Security**: API keys and Telegram tokens stored in `.env`. No sensitive data logged. Input sanitization enforced.
- **Maintainability**: Modular agent design, clear separation of concerns, comprehensive logging, and easy configuration updates without code changes.
