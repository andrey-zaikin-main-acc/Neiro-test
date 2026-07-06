import json
from pathlib import Path


def normalize_processing_result(raw: dict) -> dict:
    bom_rows = raw.get("bom_rows", [])
    normalized_rows = []
    for row in bom_rows:
        normalized_rows.append({
            "designator": str(row.get("designator", "")).strip().upper(),
            "part_number": str(row.get("part_number", "")).strip(),
            "quantity": int(row.get("quantity", 0) or 0),
        })
    return {
        "source_file": raw.get("source_file"),
        "model": raw.get("model"),
        "bom_rows": normalized_rows,
        "tables_detected": raw.get("tables_detected", len(normalized_rows) > 0),
        "images_detected": raw.get("images_detected", 0),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
