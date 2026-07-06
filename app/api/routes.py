from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.services.adapters import ADAPTERS
from app.services.normalization import normalize_processing_result, write_json
from app.services.pdf_metadata import inspect_pdf
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
    },
)


@router.post("/upload")
async def upload_pdf(kit: str = Form(...), stage_model: str = Form(...), file: UploadFile = File(...)):
    if file.content_type not in {"application/pdf", "application/octet-stream"} and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    original_filename = Path(file.filename).name
    run_id = uuid4().hex
    input_path = DATA_DIR / "input" / f"{Path(original_filename).stem}-{run_id}{Path(original_filename).suffix}"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_bytes(await file.read())
    metadata = inspect_pdf(input_path)
    adapter = ADAPTERS.get(stage_model)
    if adapter is None:
        raise HTTPException(status_code=400, detail="Unknown stage/model")
    raw, seconds = adapter.process(input_path, metadata)
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
        "visual_input": describe_visual_input(stage_model, metadata), "visual_tokens": None, "wall_clock_seconds": seconds,
        "raw_output_path": str(raw_path), "normalized_output_path": str(normalized_path), "result": "mock_completed",
        "critical_errors": 0,
    })
    return RedirectResponse("/", status_code=303)


def describe_visual_input(stage_model: str, metadata: dict) -> str:
    if stage_model != "qwen3-vl":
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
def manual_update(run_id: int, input_text_tokens: int | None = Form(None), output_text_tokens: int | None = Form(None), visual_tokens: int | None = Form(None), critical_errors: int | None = Form(None), final_score: float | None = Form(None), result: str | None = Form(None), input_summary: str | None = Form(None), short_result: str | None = Form(None), critical_issues: str | None = Form(None), suitability: str | None = Form(None)):
    update_run(run_id, locals() | {"id": None})
    return RedirectResponse("/", status_code=303)


@router.get("/export.csv")
def export_csv():
    path = export_runs_csv(DATA_DIR / "reports" / "test_runs.csv")
    return FileResponse(path, media_type="text/csv", filename="test_runs.csv")
