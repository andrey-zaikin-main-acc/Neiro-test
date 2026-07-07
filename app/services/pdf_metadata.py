from pathlib import Path
from pypdf import PdfReader


def inspect_pdf(path: Path) -> dict:
    reader = PdfReader(str(path))
    image_count = 0
    for page in reader.pages:
        try:
            image_count += len(page.images)
        except Exception:
            pass
    return {"file_name": path.name, "file_size": path.stat().st_size, "page_count": len(reader.pages), "image_count": image_count, "table_count": None}


def inspect_file(path: Path, content_type: str | None = None) -> dict:
    if content_type == "application/pdf" or path.suffix.lower() == ".pdf":
        return inspect_pdf(path)
    image_count = 1 if content_type in {"image/png", "image/jpeg"} or path.suffix.lower() in {".png", ".jpg", ".jpeg"} else 0
    return {"file_name": path.name, "file_size": path.stat().st_size, "page_count": 0, "image_count": image_count, "table_count": None}
