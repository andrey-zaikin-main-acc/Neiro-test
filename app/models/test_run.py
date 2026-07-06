from datetime import datetime
from pydantic import BaseModel, Field


class TestRunBase(BaseModel):
    kit: str = Field(..., description="Комплект КД")
    stage_model: str = Field(..., description="Этап/модель обработки")
    file_name: str
    file_count: int = 1
    page_count: int = 0
    image_count: int | None = None
    table_count: int | None = None
    input_text_tokens: int | None = None
    output_text_tokens: int | None = None
    visual_input: bool = False
    visual_tokens: int | None = None
    wall_clock_seconds: float | None = None
    raw_output_path: str | None = None
    normalized_output_path: str | None = None
    result: str = "mock_completed"
    critical_errors: int = 0
    final_score: float | None = None


class TestRunCreate(TestRunBase):
    pass


class TestRunUpdate(BaseModel):
    input_text_tokens: int | None = None
    output_text_tokens: int | None = None
    visual_tokens: int | None = None
    critical_errors: int | None = None
    final_score: float | None = None
    result: str | None = None


class TestRun(TestRunBase):
    id: int
    created_at: datetime
