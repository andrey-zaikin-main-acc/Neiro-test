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
    return {
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "page_count": len(reader.pages),
        "image_count": image_count,
        "table_count": 0,
    }
