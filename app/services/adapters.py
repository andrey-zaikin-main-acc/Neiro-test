from abc import ABC, abstractmethod
from pathlib import Path
from app.services.metrics import measure_wall_clock


class ProcessingAdapter(ABC):
    model_name: str

    @abstractmethod
    def process(self, file_path: Path, metadata: dict) -> tuple[dict, float]:
        raise NotImplementedError


class MockAdapter(ProcessingAdapter):
    model_name = "mock"

    def process(self, file_path: Path, metadata: dict) -> tuple[dict, float]:
        with measure_wall_clock() as metric:
            payload = {
                "model": self.model_name,
                "source_file": file_path.name,
                "pages": metadata.get("page_count", 0),
                "images_detected": metadata.get("image_count") or 0,
                "tables_detected": bool(metadata.get("table_count")),
                "bom_rows": [
                    {"designator": "R1", "part_number": "RC0603FR-0710KL", "quantity": 4},
                    {"designator": "C1", "part_number": "CL10B104KB8NNNC", "quantity": 2},
                ],
                "notes": "Mock response for local MVP without external model calls.",
            }
        return payload, metric.seconds


class MinerUAdapter(MockAdapter):
    model_name = "MinerU"


class PaddleOCRAdapter(MockAdapter):
    model_name = "PaddleOCR"


class Qwen3VLAdapter(MockAdapter):
    model_name = "Qwen3-VL"


class Qwen3TextAdapter(MockAdapter):
    model_name = "Qwen3-8B-text"


ADAPTERS = {
    "mineru": MinerUAdapter(),
    "paddleocr": PaddleOCRAdapter(),
    "qwen3-vl": Qwen3VLAdapter(),
    "qwen3-text": Qwen3TextAdapter(),
}
