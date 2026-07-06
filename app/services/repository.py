import csv
from pathlib import Path
from app.db import get_connection

FIELDS = ["id","kit","stage_model","file_name","file_count","page_count","image_count","table_count","input_text_tokens","output_text_tokens","visual_input","visual_tokens","wall_clock_seconds","raw_output_path","normalized_output_path","result","critical_errors","final_score","input_summary","short_result","critical_issues","suitability","created_at"]


def create_run(data: dict) -> int:
    keys = [k for k in FIELDS if k not in {"id", "created_at"}]
    values = [data.get(k) for k in keys]
    placeholders = ",".join("?" for _ in keys)
    with get_connection() as conn:
        cur = conn.execute(f"INSERT INTO test_runs ({','.join(keys)}) VALUES ({placeholders})", values)
        return int(cur.lastrowid)


def update_run(run_id: int, updates: dict) -> None:
    clean = {k: v for k, v in updates.items() if v is not None and k in FIELDS}
    if not clean:
        return
    assignments = ",".join(f"{k}=?" for k in clean)
    with get_connection() as conn:
        conn.execute(f"UPDATE test_runs SET {assignments} WHERE id=?", [*clean.values(), run_id])


def list_runs() -> list[dict]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM test_runs ORDER BY created_at DESC, id DESC")]


def export_runs_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list_runs()
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path
