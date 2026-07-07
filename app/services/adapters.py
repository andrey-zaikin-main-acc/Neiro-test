import base64
import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from app.services.metrics import measure_wall_clock

REMOTE_API_ERROR = "Для модели не настроен endpoint или API-ключ"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_UNAVAILABLE_ERROR = "Ollama недоступна по адресу {url}. Запустите Ollama локально и проверьте модель."


def check_ollama_available(base_url: str = DEFAULT_OLLAMA_BASE_URL, timeout: float = 2.0) -> dict:
    url = f"{base_url.rstrip('/')}/api/tags"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"available": True, "status_code": response.status, "base_url": base_url}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return {"available": False, "base_url": base_url, "error": str(exc), "message": OLLAMA_UNAVAILABLE_ERROR.format(url=base_url)}


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in {0xD8, 0xD9}:
                continue
            size = int.from_bytes(data[i:i + 2], "big")
            if 0xC0 <= marker <= 0xC3 and i + 7 < len(data):
                return int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 3:i + 5], "big")
            i += size
    return None, None


def post_ollama_chat(base_url: str, payload: dict, timeout: float = 120.0) -> dict:
    url = f"{base_url.rstrip('/')}/api/chat"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise ConnectionError(OLLAMA_UNAVAILABLE_ERROR.format(url=base_url)) from exc


class ProcessingAdapter(ABC):
    provider: ClassVar[str]
    model_id: ClassVar[str]
    model_revision: ClassVar[str] = ""
    quantization: ClassVar[str | None] = None
    allowed_source_types: ClassVar[set[str]]
    prompt_version: ClassVar[str] = "v1"

    @property
    def model_name(self) -> str:
        return self.model_id

    def process(self, file_path: Path, metadata: dict) -> tuple[dict, float]:
        execution_mode = metadata.get("execution_mode", "mock")
        source_type = metadata.get("source_type") or self.default_source_type
        self.validate_source_type(source_type)
        if execution_mode == "remote_api":
            return self.remote_api_error(file_path, metadata, source_type)
        if execution_mode == "local_cpu":
            return self.local_cpu_process(file_path, metadata, source_type)
        if execution_mode in {"mock", "manual_import"}:
            return self.mock_process(file_path, metadata, source_type)
        raise ValueError(f"Unknown execution_mode: {execution_mode}")

    @property
    def default_source_type(self) -> str:
        return next(iter(self.allowed_source_types))

    def validate_source_type(self, source_type: str) -> None:
        if source_type not in self.allowed_source_types:
            allowed = ", ".join(sorted(self.allowed_source_types))
            raise ValueError(f"{self.model_id} accepts only: {allowed}")

    def remote_api_error(self, file_path: Path, metadata: dict, source_type: str) -> tuple[dict, float]:
        with measure_wall_clock() as metric:
            payload = self.base_payload(file_path, metadata, source_type) | {"status": "configuration_error", "error": REMOTE_API_ERROR, "bom_rows": [], "notes": "Remote API calls are not implemented in this test bench yet."}
        return payload, metric.seconds

    def local_cpu_process(self, file_path: Path, metadata: dict, source_type: str) -> tuple[dict, float]:
        return self.mock_process(file_path, metadata, source_type)

    def mock_process(self, file_path: Path, metadata: dict, source_type: str) -> tuple[dict, float]:
        with measure_wall_clock() as metric:
            payload = self.base_payload(file_path, metadata, source_type) | self.mock_payload(metadata)
        return payload, metric.seconds

    def base_payload(self, file_path: Path, metadata: dict, source_type: str) -> dict:
        return {"provider": self.provider, "model": self.model_id, "model_id": self.model_id, "model_revision": self.model_revision, "quantization": self.quantization, "execution_mode": metadata.get("execution_mode", "mock"), "source_type": source_type, "prompt_version": metadata.get("prompt_version") or self.prompt_version, "source_file": file_path.name, "pages": metadata.get("page_count", 0)}

    @abstractmethod
    def mock_payload(self, metadata: dict) -> dict:
        raise NotImplementedError


class MockBOMMixin:
    def mock_payload(self, metadata: dict) -> dict:
        return {"images_detected": metadata.get("image_count") or 0, "tables_detected": bool(metadata.get("table_count")), "bom_rows": [{"designator": "R1", "part_number": "RC0603FR-0710KL", "quantity": 4}, {"designator": "C1", "part_number": "CL10B104KB8NNNC", "quantity": 2}], "notes": "Mock response for local MVP without external model calls."}


class PPDocLayoutLAdapter(ProcessingAdapter):
    provider = "PaddlePaddle"
    model_id = "PP-DocLayout-L"
    allowed_source_types = {"изображение"}

    def mock_payload(self, metadata: dict) -> dict:
        pages = max(int(metadata.get("page_count") or 0), 1)
        return {"page_blocks": [{"block_type": "page_mock_region", "coordinates": [0, 0, 100, 100], "page_number": page, "confidence": 0.99} for page in range(1, pages + 1)], "bom_rows": [], "images_detected": metadata.get("image_count") or pages, "tables_detected": False, "notes": "PP-DocLayout-L mock: page image layout blocks only."}


class MinerU25Adapter(MockBOMMixin, ProcessingAdapter):
    provider = "MinerU"
    model_id = "MinerU 2.5"
    allowed_source_types = {"PDF"}


class Qwen3VL8BAdapter(MockBOMMixin, ProcessingAdapter):
    provider = "Ollama"
    model_id = "qwen3-vl:8b"
    model_revision = "901cae732162"
    quantization = "Q4_K_M"
    allowed_source_types = {"изображение", "crop-фрагмент"}

    def local_cpu_process(self, file_path: Path, metadata: dict, source_type: str) -> tuple[dict, float]:
        if metadata.get("content_type") not in {"image/png", "image/jpeg"} and file_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("Qwen3-VL local_cpu accepts only PNG/JPEG images")
        width, height = image_dimensions(file_path)
        image_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
        prompt = metadata.get("prompt") or "Проанализируй изображение страницы или crop-фрагмента КД и верни структурированный результат."
        request_payload = {"model": self.model_id, "stream": False, "messages": [{"role": "user", "content": prompt, "images": [image_b64]}]}
        start = time.perf_counter()
        raw = post_ollama_chat(os.getenv("QWEN3_VL_BASE_URL", DEFAULT_OLLAMA_BASE_URL), request_payload)
        seconds = time.perf_counter() - start
        return self.base_payload(file_path, metadata, source_type) | self.ollama_metrics(raw) | {"status": "completed", "raw_ollama_json": raw, "visual_tokens": None, "visual_input": {"image_count": 1, "width": width, "height": height}, "bom_rows": [], "notes": "Ollama local Qwen3-VL response saved as raw_ollama_json."}, seconds

    def ollama_metrics(self, raw: dict) -> dict:
        return {"input_text_tokens": raw.get("prompt_eval_count"), "output_text_tokens": raw.get("eval_count"), "total_duration": raw.get("total_duration"), "load_duration": raw.get("load_duration"), "prompt_eval_duration": raw.get("prompt_eval_duration"), "eval_duration": raw.get("eval_duration")}


class Qwen25_3BAdapter(ProcessingAdapter):
    provider = "Ollama"
    model_id = "qwen2.5:3b"
    model_revision = "357c53fb659c"
    quantization = "Q4_K_M"
    allowed_source_types = {"очищенный JSON"}
    allowed_tasks = ["статус комплекта", "найденные документы", "неподтверждённые документы", "риски", "вопросы клиенту", "краткая рекомендация"]

    def local_cpu_process(self, file_path: Path, metadata: dict, source_type: str) -> tuple[dict, float]:
        if file_path.suffix.lower() == ".pdf" or metadata.get("content_type") == "application/pdf":
            raise ValueError("Qwen2.5-3B accepts only cleaned JSON, not PDF")
        text = file_path.read_text(encoding="utf-8")
        if "<html" in text.lower() or "<!doctype html" in text.lower():
            raise ValueError("Qwen2.5-3B accepts only cleaned JSON, not raw HTML")
        json.loads(text)
        prompt = "Используй только очищенный JSON. Не извлекай и не пересчитывай BOM. Верни только: статус комплекта, найденные документы, неподтверждённые документы, риски, вопросы клиенту, краткая рекомендация.\n" + text
        request_payload = {"model": self.model_id, "stream": False, "format": "json", "messages": [{"role": "user", "content": prompt}]}
        start = time.perf_counter()
        raw = post_ollama_chat(os.getenv("QWEN25_3B_BASE_URL", DEFAULT_OLLAMA_BASE_URL), request_payload)
        seconds = time.perf_counter() - start
        return self.base_payload(file_path, metadata, source_type) | {"status": "completed", "raw_ollama_json": raw, "allowed_tasks": self.allowed_tasks, "input_text_tokens": raw.get("prompt_eval_count"), "output_text_tokens": raw.get("eval_count"), "bom_rows": [], "notes": "BOM extraction and recalculation are forbidden for this adapter."}, seconds

    def mock_payload(self, metadata: dict) -> dict:
        return {"allowed_tasks": self.allowed_tasks, "kit_status": "mock: требуется ручная проверка", "found_documents": [], "unconfirmed_documents": [], "risks": ["mock: часть данных не подтверждена"], "questions_to_client": ["mock: подтвердите актуальность комплекта КД"], "short_recommendation": "mock: использовать только после MinerU/Qwen3-VL и очистки JSON/текста", "bom_rows": [], "images_detected": 0, "tables_detected": False, "notes": "Qwen2.5-3B must not extract BOM directly from raw MinerU HTML."}


ADAPTERS = {"pp-doclayout-l": PPDocLayoutLAdapter(), "mineru-2.5": MinerU25Adapter(), "qwen3-vl-8b": Qwen3VL8BAdapter(), "qwen2.5-3b": Qwen25_3BAdapter(), "mineru": MinerU25Adapter(), "qwen3-vl": Qwen3VL8BAdapter()}
EXECUTION_MODES = ["mock", "remote_api", "manual_import", "local_cpu"]
SOURCE_TYPES = ["PDF", "изображение", "crop-фрагмент", "очищенный JSON"]
