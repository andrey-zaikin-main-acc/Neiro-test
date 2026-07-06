from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from app.services.metrics import measure_wall_clock

REMOTE_API_ERROR = "Для модели не настроен endpoint или API-ключ"


class ProcessingAdapter(ABC):
    """Base adapter contract for planned model integrations.

    Real endpoints are intentionally not wired yet: mock mode remains deterministic,
    while remote_api reports a clear configuration error.
    """

    provider: ClassVar[str]
    model_id: ClassVar[str]
    model_revision: ClassVar[str] = ""
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
        if execution_mode in {"mock", "manual_import", "local_cpu"}:
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
            payload = self.base_payload(file_path, metadata, source_type) | {
                "status": "configuration_error",
                "error": REMOTE_API_ERROR,
                "bom_rows": [],
                "notes": "Remote API calls are not implemented in this test bench yet.",
            }
        return payload, metric.seconds

    def mock_process(self, file_path: Path, metadata: dict, source_type: str) -> tuple[dict, float]:
        with measure_wall_clock() as metric:
            payload = self.base_payload(file_path, metadata, source_type) | self.mock_payload(metadata)
        return payload, metric.seconds

    def base_payload(self, file_path: Path, metadata: dict, source_type: str) -> dict:
        return {
            "provider": self.provider,
            "model": self.model_id,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "execution_mode": metadata.get("execution_mode", "mock"),
            "source_type": source_type,
            "prompt_version": metadata.get("prompt_version") or self.prompt_version,
            "source_file": file_path.name,
            "pages": metadata.get("page_count", 0),
        }

    @abstractmethod
    def mock_payload(self, metadata: dict) -> dict:
        raise NotImplementedError


class MockBOMMixin:
    def mock_payload(self, metadata: dict) -> dict:
        return {
            "images_detected": metadata.get("image_count") or 0,
            "tables_detected": bool(metadata.get("table_count")),
            "bom_rows": [
                {"designator": "R1", "part_number": "RC0603FR-0710KL", "quantity": 4},
                {"designator": "C1", "part_number": "CL10B104KB8NNNC", "quantity": 2},
            ],
            "notes": "Mock response for local MVP without external model calls.",
        }


class PPDocLayoutLAdapter(ProcessingAdapter):
    provider = "PaddlePaddle"
    model_id = "PP-DocLayout-L"
    allowed_source_types = {"изображение"}

    def mock_payload(self, metadata: dict) -> dict:
        pages = max(int(metadata.get("page_count") or 0), 1)
        return {
            "page_blocks": [
                {
                    "block_type": "page_mock_region",
                    "coordinates": [0, 0, 100, 100],
                    "page_number": page,
                    "confidence": 0.99,
                }
                for page in range(1, pages + 1)
            ],
            "bom_rows": [],
            "images_detected": metadata.get("image_count") or pages,
            "tables_detected": False,
            "notes": "PP-DocLayout-L mock: page image layout blocks only.",
        }


class MinerU25Adapter(MockBOMMixin, ProcessingAdapter):
    provider = "MinerU"
    model_id = "MinerU 2.5"
    allowed_source_types = {"PDF"}


class Qwen3VL8BAdapter(MockBOMMixin, ProcessingAdapter):
    provider = "Qwen"
    model_id = "Qwen3-VL-8B-Instruct"
    allowed_source_types = {"изображение", "crop-фрагмент"}


class Qwen25_3BAdapter(ProcessingAdapter):
    provider = "Qwen"
    model_id = "Qwen2.5-3B-Instruct"
    allowed_source_types = {"очищенный JSON"}
    allowed_tasks = [
        "статус комплекта",
        "найденные документы",
        "неподтверждённые документы",
        "риски",
        "вопросы клиенту",
        "краткая рекомендация",
    ]

    def mock_payload(self, metadata: dict) -> dict:
        return {
            "allowed_tasks": self.allowed_tasks,
            "kit_status": "mock: требуется ручная проверка",
            "found_documents": [],
            "unconfirmed_documents": [],
            "risks": ["mock: часть данных не подтверждена"],
            "questions_to_client": ["mock: подтвердите актуальность комплекта КД"],
            "short_recommendation": "mock: использовать только после MinerU/Qwen3-VL и очистки JSON/текста",
            "bom_rows": [],
            "images_detected": 0,
            "tables_detected": False,
            "notes": "Qwen2.5-3B must not extract BOM directly from raw MinerU HTML.",
        }


ADAPTERS = {
    "pp-doclayout-l": PPDocLayoutLAdapter(),
    "mineru-2.5": MinerU25Adapter(),
    "qwen3-vl-8b": Qwen3VL8BAdapter(),
    "qwen2.5-3b": Qwen25_3BAdapter(),
    # Legacy aliases keep existing mock-mode tests and old links working.
    "mineru": MinerU25Adapter(),
    "qwen3-vl": Qwen3VL8BAdapter(),
}

EXECUTION_MODES = ["mock", "remote_api", "manual_import", "local_cpu"]
SOURCE_TYPES = ["PDF", "изображение", "crop-фрагмент", "очищенный JSON"]
