import csv
from pathlib import Path
from app.db import get_connection

FIELDS = ["id","kit","stage_model","file_name","file_count","page_count","image_count","table_count","input_text_tokens","output_text_tokens","visual_input","visual_tokens","wall_clock_seconds","raw_output_path","normalized_output_path","result","critical_errors","final_score","input_summary","short_result","critical_issues","suitability","provider","model_id","model_revision","execution_mode","source_type","parent_run_id","prompt_version","total_duration","load_duration","prompt_eval_duration","eval_duration","quantization","pipeline_run_id","input_file_id","created_at"]


def create_run(data: dict) -> int:
    keys = [k for k in FIELDS if k not in {"id", "created_at"}]
    values = [("mock" if k == "execution_mode" and data.get(k) is None else data.get(k)) for k in keys]
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


def create_pipeline_run(data: dict) -> None:
    keys=["id","kit","status","started_at","finished_at","total_wall_clock_seconds","final_report_json_path","final_report_md_path","error_message"]
    with get_connection() as conn:
        conn.execute(f"INSERT OR REPLACE INTO pipeline_runs ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [data.get(k) for k in keys])

def create_input_file(data: dict) -> None:
    keys=["id","pipeline_run_id","original_filename","saved_path","extension","mime_type","file_size_bytes","detected_document_type","page_count","sheet_count","image_count","table_count","processing_status","error_message"]
    with get_connection() as conn:
        conn.execute(f"INSERT OR REPLACE INTO input_files ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [data.get(k) for k in keys])

def list_pipeline_runs() -> list[dict]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM pipeline_runs ORDER BY started_at DESC")]
