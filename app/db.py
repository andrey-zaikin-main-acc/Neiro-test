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
            visual_input TEXT NOT NULL DEFAULT 'не использовался',
            visual_tokens INTEGER,
            wall_clock_seconds REAL,
            raw_output_path TEXT,
            normalized_output_path TEXT,
            result TEXT NOT NULL,
            critical_errors INTEGER NOT NULL DEFAULT 0,
            final_score REAL,
            input_summary TEXT,
            short_result TEXT,
            critical_issues TEXT,
            suitability TEXT,
            provider TEXT,
            model_id TEXT,
            model_revision TEXT,
            execution_mode TEXT NOT NULL DEFAULT 'mock',
            source_type TEXT,
            parent_run_id INTEGER,
            prompt_version TEXT,
            total_duration INTEGER,
            load_duration INTEGER,
            prompt_eval_duration INTEGER,
            eval_duration INTEGER,
            quantization TEXT,
            pipeline_run_id TEXT,
            input_file_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        _ensure_column(conn, "input_summary", "TEXT")
        _ensure_column(conn, "short_result", "TEXT")
        _ensure_column(conn, "critical_issues", "TEXT")
        _ensure_column(conn, "suitability", "TEXT")
        _ensure_column(conn, "provider", "TEXT")
        _ensure_column(conn, "model_id", "TEXT")
        _ensure_column(conn, "model_revision", "TEXT")
        _ensure_column(conn, "execution_mode", "TEXT NOT NULL DEFAULT 'mock'")
        _ensure_column(conn, "source_type", "TEXT")
        _ensure_column(conn, "parent_run_id", "INTEGER")
        _ensure_column(conn, "prompt_version", "TEXT")
        _ensure_column(conn, "total_duration", "INTEGER")
        _ensure_column(conn, "load_duration", "INTEGER")
        _ensure_column(conn, "prompt_eval_duration", "INTEGER")
        _ensure_column(conn, "eval_duration", "INTEGER")
        _ensure_column(conn, "quantization", "TEXT")
        _ensure_column(conn, "pipeline_run_id", "TEXT")
        _ensure_column(conn, "input_file_id", "TEXT")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY, kit TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT, finished_at TEXT,
            total_wall_clock_seconds REAL, final_report_json_path TEXT, final_report_md_path TEXT, error_message TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS input_files (
            id TEXT PRIMARY KEY, pipeline_run_id TEXT NOT NULL, original_filename TEXT NOT NULL, saved_path TEXT NOT NULL,
            extension TEXT, mime_type TEXT, file_size_bytes INTEGER, detected_document_type TEXT, page_count INTEGER,
            sheet_count INTEGER, image_count INTEGER, table_count INTEGER, processing_status TEXT, error_message TEXT
        )
        """)


def _ensure_column(conn: sqlite3.Connection, column_name: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(test_runs)")}
    if column_name not in existing:
        conn.execute(f"ALTER TABLE test_runs ADD COLUMN {column_name} {definition}")
