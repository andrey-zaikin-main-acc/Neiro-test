from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.services.adapters import ADAPTERS, EXECUTION_MODES, SOURCE_TYPES, DEFAULT_OLLAMA_BASE_URL, check_ollama_available
from app.services.normalization import normalize_processing_result, write_json
from app.services.pdf_metadata import inspect_file
from app.services.repository import create_run, export_runs_csv, list_runs, update_run
from app.models.test_run import TestRunUpdate

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
DATA_DIR = Path("data")


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={
        "runs": list_runs(),
        "models": list(ADAPTERS.keys()),
        "execution_modes": EXECUTION_MODES,
        "source_types": SOURCE_TYPES,
        "ollama_status": check_ollama_available(),
    },
)


@router.post("/upload")
async def upload_file(kit: str = Form(...), stage_model: str = Form(...), execution_mode: str = Form("mock"), source_type: str | None = Form(None), parent_run_id: int | None = Form(None), prompt_version: str | None = Form(None), file: UploadFile = File(...)):
    original_filename = Path(file.filename).name
    run_id = uuid4().hex
    input_path = DATA_DIR / "input" / f"{Path(original_filename).stem}-{run_id}{Path(original_filename).suffix}"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_bytes(await file.read())
    metadata = inspect_file(input_path, file.content_type)
    adapter = ADAPTERS.get(stage_model)
    if adapter is None:
        raise HTTPException(status_code=400, detail="Unknown stage/model")
    if execution_mode not in EXECUTION_MODES:
        raise HTTPException(status_code=400, detail="Unknown execution mode")
    source_type = source_type or adapter.default_source_type
    metadata = metadata | {"execution_mode": execution_mode, "source_type": source_type, "prompt_version": prompt_version, "content_type": file.content_type}
    try:
        raw, seconds = adapter.process(input_path, metadata)
    except (ValueError, ConnectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized = normalize_processing_result(raw)
    stem = Path(original_filename).stem
    output_name = f"{stem}-{stage_model}-{run_id}.json"
    raw_path = DATA_DIR / "raw_output" / output_name
    normalized_path = DATA_DIR / "normalized" / output_name
    write_json(raw_path, raw)
    write_json(normalized_path, normalized)
    create_run({
        "kit": kit, "stage_model": stage_model, "file_name": original_filename, "file_count": 1,
        "page_count": metadata["page_count"], "image_count": metadata["image_count"], "table_count": metadata["table_count"],
        "visual_input": describe_visual_input(stage_model, metadata, raw), "visual_tokens": raw.get("visual_tokens"), "wall_clock_seconds": seconds,
        "raw_output_path": str(raw_path), "normalized_output_path": str(normalized_path), "result": raw.get("status", "mock_completed"),
        "critical_errors": 0,
        "provider": adapter.provider, "model_id": adapter.model_id, "model_revision": adapter.model_revision,
        "execution_mode": execution_mode, "source_type": source_type, "parent_run_id": parent_run_id,
        "prompt_version": prompt_version or adapter.prompt_version,
        "input_text_tokens": raw.get("input_text_tokens"), "output_text_tokens": raw.get("output_text_tokens"),
        "total_duration": raw.get("total_duration"), "load_duration": raw.get("load_duration"),
        "prompt_eval_duration": raw.get("prompt_eval_duration"), "eval_duration": raw.get("eval_duration"),
        "quantization": raw.get("quantization") or adapter.quantization,
    })
    return RedirectResponse("/", status_code=303)


def describe_visual_input(stage_model: str, metadata: dict, raw: dict | None = None) -> str:
    if raw and isinstance(raw.get("visual_input"), dict):
        visual = raw["visual_input"]
        return f"{visual.get('image_count', 0)} изображений; ширина={visual.get('width')}; высота={visual.get('height')}"
    if stage_model not in {"qwen3-vl", "qwen3-vl-8b"}:
        return "не использовался"
    image_count = metadata.get("image_count") or 0
    page_count = metadata.get("page_count") or 0
    if image_count == 1:
        return "1 изображение (размер не определён)"
    if page_count == 1:
        return "1 страница PDF"
    return f"{page_count} страниц PDF"


@router.get("/api/test-runs")
def api_list_runs():
    return list_runs()


@router.patch("/api/test-runs/{run_id}")
def api_update_run(run_id: int, payload: TestRunUpdate):
    update_run(run_id, payload.model_dump(exclude_unset=True))
    return {"status": "ok"}


@router.post("/test-runs/{run_id}/manual")
def manual_update(run_id: int, input_text_tokens: int | None = Form(None), output_text_tokens: int | None = Form(None), visual_tokens: int | None = Form(None), critical_errors: int | None = Form(None), final_score: float | None = Form(None), result: str | None = Form(None), input_summary: str | None = Form(None), short_result: str | None = Form(None), critical_issues: str | None = Form(None), suitability: str | None = Form(None), provider: str | None = Form(None), model_id: str | None = Form(None), model_revision: str | None = Form(None), execution_mode: str | None = Form(None), source_type: str | None = Form(None), parent_run_id: int | None = Form(None), prompt_version: str | None = Form(None)):
    update_run(run_id, locals() | {"id": None})
    return RedirectResponse("/", status_code=303)


@router.get("/export.csv")
def export_csv():
    path = export_runs_csv(DATA_DIR / "reports" / "test_runs.csv")
    return FileResponse(path, media_type="text/csv", filename="test_runs.csv")


@router.get("/api/ollama/status")
def api_ollama_status():
    return check_ollama_available(DEFAULT_OLLAMA_BASE_URL)
