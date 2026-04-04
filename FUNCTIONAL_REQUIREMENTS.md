# Functional Requirement Specification: Agentic News Aggregator & Summarizer

## 1. System Overview
An automated, agent-driven news monitoring system that polls RSS feeds every 15 minutes, filters for market-relevant content, summarizes facts strictly, tracks subject evolution, analyzes investment impact, and delivers structured status updates via Telegram.

## 2. Data Ingestion & Filtering
- **Sources**: RSS feeds from reputable financial, geopolitical, and macroeconomic news outlets.
- **Polling Interval**: Fixed 15-minute schedule.
- **Filtering Rules**:
  - Include: Geopolitics, Macroeconomics, Central Banks, Corporate Earnings, Tech/Supply Chain, Commodities, Forex, Crypto.
  - Exclude: Sports, Entertainment, Lifestyle, Celebrity News, Pure Opinion/Editorials.
  - Deduplication: Remove exact or near-duplicate headlines across sources before processing.

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

## 4. Subject Tracking & Clustering
- **Hybrid Approach**:
  - **Predefined Watchlist**: Core subjects tracked explicitly (e.g., "Fed Interest Rates", "US-China Trade", "NVIDIA/AI Chips", "Oil Prices").
  - **Dynamic Detection**: LLM automatically identifies and names emerging topics not on the watchlist, adding them to the tracking pool if they meet relevance thresholds.
- **State Management**: Each subject maintains a `latest_status`, `last_updated`, `impact_level`, and `development_history`.

## 5. Output & Delivery
- **Platform**: Telegram Bot.
- **Trigger**: Every 15 minutes after processing completes.
- **Format**: Structured status report.
  - Unchanged subjects: Display current status concisely.
  - New developments: Highlight with clear markers (e.g., `🔴 NEW DEVELOPMENT:` or `⚡ UPDATE:`).
  - Grouped by impact level or sector for readability.
- **Commands**: `/start`, `/status`, `/watchlist`, `/help`.

## 6. Data Storage
- **Database**: SQLite.
- **Tables**: `subjects`, `articles`, `subject_history`, `watchlist`.
- **Retention**: Configurable (default: 30 days) to manage DB size and context window limits.

## 7. Non-Functional Requirements
- **Reliability**: Graceful handling of RSS feed failures, API rate limits, and LLM timeouts. Retry logic with exponential backoff.
- **Cost Efficiency**: Optimized for OpenRouter free tier (`qwen/qwen3.6-plus:free`). Token usage minimized via strict prompt engineering and context truncation.
- **Latency**: Full pipeline (fetch → process → send) must complete within 5 minutes to allow buffer before next poll.
- **Security**: API keys and Telegram tokens stored in `.env`. No sensitive data logged.
