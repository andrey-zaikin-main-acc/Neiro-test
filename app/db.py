import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", "data/testbench.sqlite3"))


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kit TEXT NOT NULL,
            stage_model TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_count INTEGER NOT NULL,
            page_count INTEGER NOT NULL,
            image_count INTEGER,
            table_count INTEGER,
            input_text_tokens INTEGER,
            output_text_tokens INTEGER,
            visual_input INTEGER NOT NULL DEFAULT 0,
            visual_tokens INTEGER,
            wall_clock_seconds REAL,
            raw_output_path TEXT,
            normalized_output_path TEXT,
            result TEXT NOT NULL,
            critical_errors INTEGER NOT NULL DEFAULT 0,
            final_score REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
