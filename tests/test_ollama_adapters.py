import json
import urllib.error

from fastapi.testclient import TestClient

import app.api.routes as routes
import app.db as db
import app.services.adapters as adapters
import app.services.repository as repo
from app.main import app
from tests.test_upload_app import configure_tmp_app, make_pdf


def png_bytes(width=1, height=1):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00" + b"rest"


class FakeHTTPResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def mock_ollama(monkeypatch, payload=None):
    payload = payload or {
        "message": {"content": "{}"},
        "prompt_eval_count": 11,
        "eval_count": 7,
        "total_duration": 100,
        "load_duration": 20,
        "prompt_eval_duration": 30,
        "eval_duration": 40,
    }

    def fake_urlopen(request, timeout=120):
        return FakeHTTPResponse(payload)

    monkeypatch.setattr(adapters.urllib.request, "urlopen", fake_urlopen)


def test_qwen3_vl_accepts_image_and_transfers_tokens_and_durations(tmp_path, monkeypatch):
    configure_tmp_app(tmp_path, monkeypatch)
    mock_ollama(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/upload",
            data={"kit": "kit", "stage_model": "qwen3-vl-8b", "execution_mode": "local_cpu", "source_type": "изображение"},
            files={"file": ("page.png", png_bytes(2, 3), "image/png")},
            follow_redirects=False,
        )
    assert response.status_code == 303
    run = repo.list_runs()[0]
    assert run["input_text_tokens"] == 11
    assert run["output_text_tokens"] == 7
    assert run["total_duration"] == 100
    assert run["load_duration"] == 20
    assert run["prompt_eval_duration"] == 30
    assert run["eval_duration"] == 40
    assert run["provider"] == "Ollama"
    assert run["model_id"] == "qwen3-vl:8b"
    assert run["model_revision"] == "901cae732162"
    assert run["quantization"] == "Q4_K_M"
    assert "ширина=2" in run["visual_input"]
    raw = json.loads((tmp_path / run["raw_output_path"]).read_text(encoding="utf-8")) if not str(run["raw_output_path"]).startswith(str(tmp_path)) else json.loads(open(run["raw_output_path"], encoding="utf-8").read())
    assert raw["raw_ollama_json"]["prompt_eval_count"] == 11


def test_qwen25_rejects_pdf_and_raw_html(tmp_path, monkeypatch):
    configure_tmp_app(tmp_path, monkeypatch)
    pdf_bytes = make_pdf(tmp_path / "input.pdf")
    with TestClient(app) as client:
        pdf_response = client.post(
            "/upload",
            data={"kit": "kit", "stage_model": "qwen2.5-3b", "execution_mode": "local_cpu", "source_type": "очищенный JSON"},
            files={"file": ("input.pdf", pdf_bytes, "application/pdf")},
        )
        html_response = client.post(
            "/upload",
            data={"kit": "kit", "stage_model": "qwen2.5-3b", "execution_mode": "local_cpu", "source_type": "очищенный JSON"},
            files={"file": ("input.html", b"<html><body>raw</body></html>", "text/html")},
        )
    assert pdf_response.status_code == 400
    assert "not PDF" in pdf_response.json()["detail"]
    assert html_response.status_code == 400
    assert "not raw HTML" in html_response.json()["detail"]


def test_qwen25_clean_json_uses_ollama_format_json(tmp_path, monkeypatch):
    configure_tmp_app(tmp_path, monkeypatch)
    captured = {}

    def fake_post(base_url, payload, timeout=120.0):
        captured.update(payload)
        return {"message": {"content": "{}"}, "prompt_eval_count": 5, "eval_count": 3}

    monkeypatch.setattr(adapters, "post_ollama_chat", fake_post)
    with TestClient(app) as client:
        response = client.post(
            "/upload",
            data={"kit": "kit", "stage_model": "qwen2.5-3b", "execution_mode": "local_cpu", "source_type": "очищенный JSON"},
            files={"file": ("clean.json", b'{"documents": []}', "application/json")},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert captured["format"] == "json"
    assert captured["model"] == "qwen2.5:3b"


def test_ollama_unavailable_returns_clear_error(tmp_path, monkeypatch):
    configure_tmp_app(tmp_path, monkeypatch)

    def unavailable(request, timeout=120):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(adapters.urllib.request, "urlopen", unavailable)
    with TestClient(app) as client:
        response = client.post(
            "/upload",
            data={"kit": "kit", "stage_model": "qwen3-vl-8b", "execution_mode": "local_cpu", "source_type": "изображение"},
            files={"file": ("page.png", png_bytes(), "image/png")},
        )
    assert response.status_code == 400
    assert "Ollama недоступна" in response.json()["detail"]
    assert "127.0.0.1:11434" in response.json()["detail"]
