from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter

import app.api.routes as routes
import app.db as db
import app.services.repository as repo
from app.main import app


def make_pdf(path: Path) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as fh:
        writer.write(fh)
    return path.read_bytes()


def configure_tmp_app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(repo, "get_connection", db.get_connection)
    monkeypatch.setattr(routes, "DATA_DIR", tmp_path / "data")
    db.init_db()


def test_same_named_uploads_do_not_overwrite_previous_run(tmp_path, monkeypatch):
    configure_tmp_app(tmp_path, monkeypatch)
    pdf_bytes = make_pdf(tmp_path / "same.pdf")
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post(
                "/upload",
                data={"kit": "kit", "stage_model": "mineru"},
                files={"file": ("same.pdf", pdf_bytes, "application/pdf")},
                follow_redirects=False,
            )
            assert response.status_code == 303

    runs = repo.list_runs()
    assert len(runs) == 2
    raw_paths = {run["raw_output_path"] for run in runs}
    normalized_paths = {run["normalized_output_path"] for run in runs}
    assert len(raw_paths) == 2
    assert len(normalized_paths) == 2
    assert all(Path(path).exists() for path in raw_paths | normalized_paths)
    assert len(list((tmp_path / "data" / "input").glob("same-*.pdf"))) == 2


def test_app_starts_and_opens_home_page(tmp_path, monkeypatch):
    configure_tmp_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Загрузка PDF" in response.text
