"""Database schema and shared constants (single source of truth)."""

from datetime import datetime, timezone

DURATIONS = (10, 20, 30, 45, 60)
INTERESTS = (
    "nature discovery",
    "bird watching",
    "plants",
    "mindfulness",
    "photography",
    "walking",
)
DIFFICULTIES = ("easy", "medium", "adventurous")
MOODS = ("calm", "happy", "energized", "curious", "grateful", "tired", "neutral")
MISSION_STATUSES = ("created", "started", "completed")
MISSION_SOURCES = ("ai", "fallback")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    difficulty TEXT NOT NULL,
    interests TEXT NOT NULL,              -- JSON array of strings
    environment TEXT NOT NULL,
    tasks TEXT NOT NULL,                  -- JSON array of strings
    phone_reminder TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('ai', 'fallback')),
    model_name TEXT,                      -- set only when source = 'ai'
    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'started', 'completed')),
    completed_task_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER REFERENCES missions(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    mood TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_missions_created ON missions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_journal_created ON journal_entries(created_at DESC);
"""


def utc_now_iso() -> str:
    """Current UTC time like 2026-10-10T14:30:05Z (browser converts to local time)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")