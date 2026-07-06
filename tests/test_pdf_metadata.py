from pypdf import PdfWriter

from app.services.pdf_metadata import inspect_pdf


def test_table_count_is_null_until_ocr(tmp_path):
    pdf_path = tmp_path / "plain.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as fh:
        writer.write(fh)

    metadata = inspect_pdf(pdf_path)

    assert metadata["table_count"] is None
