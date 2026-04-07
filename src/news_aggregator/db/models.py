# src/news_aggregator/db/models.py

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    watchlist_flag BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP NOT NULL,
    latest_status TEXT,
    impact_level TEXT DEFAULT 'NONE',
    relevance_score REAL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS subject_assets (
    subject_id INTEGER NOT NULL,
    asset_ticker TEXT NOT NULL,
    FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    feed_name TEXT,
    author TEXT,
    summary_snippet TEXT,
    raw_content TEXT,
    FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS subject_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    status_snapshot TEXT NOT NULL,
    impact_level TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS history_articles (
    history_id INTEGER NOT NULL,
    article_id INTEGER NOT NULL,
    FOREIGN KEY (history_id) REFERENCES subject_history (id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_name TEXT NOT NULL UNIQUE,
    keywords TEXT NOT NULL, -- JSON array
    priority INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_reviewed TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT,
    raw_content TEXT,
    error_message TEXT,
    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_articles_subject ON articles(subject_id);
CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at);
CREATE INDEX IF NOT EXISTS idx_history_subject ON subject_history(subject_id);
CREATE INDEX IF NOT EXISTS idx_subjects_last_seen ON subjects(last_seen);
CREATE INDEX IF NOT EXISTS idx_watchlist_active ON watchlist(is_active);
CREATE INDEX IF NOT EXISTS idx_subject_assets_subject ON subject_assets(subject_id);
CREATE INDEX IF NOT EXISTS idx_history_articles_history ON history_articles(history_id);
"""
