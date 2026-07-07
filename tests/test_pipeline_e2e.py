import json, zipfile
from pathlib import Path

from pypdf import PdfWriter

import app.db as db
import app.services.repository as repo
import app.services.pipeline as pipeline


def configure(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'test.sqlite3')
    monkeypatch.setattr(repo, 'get_connection', db.get_connection)
    db.init_db()


def pdf(path):
    w=PdfWriter(); w.add_blank_page(width=72,height=72)
    with path.open('wb') as f: w.write(f)
    return path


def docx(path, text='DOCX text Gerber mentioned'):
    xml=f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
    with zipfile.ZipFile(path,'w') as z: z.writestr('word/document.xml', xml)
    return path


def xlsx(path):
    try:
        from openpyxl import Workbook
    except Exception:
        return None
    wb=Workbook(); ws=wb.active; ws.title='BOM'; ws.append(['RefDes','Value','Qty']); ws.append(['R1','10k',1]); wb.save(path); return path


def item(path, pid='seed'):
    return {'id':path.stem,'pipeline_run_id':pid,'original_filename':path.name,'saved_path':str(path),'extension':path.suffix.lower(),'mime_type':None,'file_size_bytes':path.stat().st_size}


def test_kd1_pdf_not_configured_models_still_creates_report(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch); monkeypatch.delenv('PP_DOCLAYOUT_COMMAND', raising=False); monkeypatch.delenv('MINERU_COMMAND', raising=False)
    r=pipeline.process_pipeline('КД1',[item(pdf(tmp_path/'kd1.pdf'))], tmp_path/'data')
    assert Path(r['pipeline_run']['final_report_json_path']).exists()
    assert r['pipeline_run']['status']=='completed_with_warnings'
    stages=r['per_file_results'][0]['stages']
    assert {s['status'] for s in stages}=={'not_configured'}


def test_kd2_pdf_xlsx_and_kd3_docx_supported(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    p=pdf(tmp_path/'a.pdf'); x=xlsx(tmp_path/'bom.xlsx'); d=docx(tmp_path/'manual.docx')
    files=[item(p), item(d)] + ([item(x)] if x else [])
    r=pipeline.process_pipeline('mixed', files, tmp_path/'data')
    names=[f['original_filename'] for f in r['composition']]
    assert 'a.pdf' in names and 'manual.docx' in names
    if x: assert 'bom.xlsx' in names
    assert Path(r['pipeline_run']['final_report_md_path']).exists()


def test_failed_one_file_does_not_hide_final_report(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    bad=tmp_path/'bad.docx'; bad.write_bytes(b'not a zip')
    good=pdf(tmp_path/'good.pdf')
    r=pipeline.process_pipeline('partial',[item(bad), item(good)], tmp_path/'data')
    assert Path(r['pipeline_run']['final_report_json_path']).exists()
    assert any(f['processing_status']=='inventory_failed' for f in r['composition'])


def test_qwen25_input_is_cleaned_json_not_raw_pdf_excel_html_or_markdown(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    x=xlsx(tmp_path/'bom.xlsx')
    files=[item(x)] if x else []
    r=pipeline.process_pipeline('excel', files, tmp_path/'data')
    cleaned=Path(r['per_file_results'][0]['cleaned_json_path']) if files else None
    if cleaned:
        data=json.loads(cleaned.read_text(encoding='utf-8'))
        assert data['parser_status']=='completed'
        assert cleaned.suffix=='.json'


def test_mentions_do_not_confirm_gerber_step_pickplace(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    d=docx(tmp_path/'readme.docx','Gerber STEP Pick&amp;Place BOM are mentioned only')
    r=pipeline.process_pipeline('mentions',[item(d)], tmp_path/'data')
    assert {'gerber','step','pick&place','bom'} <= set(r['final']['unconfirmed_documents'])
