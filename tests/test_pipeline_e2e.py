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
    import app.services.adapters as adapters
    monkeypatch.setattr(adapters, 'post_ollama_chat', lambda base_url, payload, timeout=120.0: fake_ollama_raw())
    r=pipeline.process_pipeline('КД1',[item(pdf(tmp_path/'kd1.pdf'))], tmp_path/'data')
    assert Path(r['pipeline_run']['final_report_json_path']).exists()
    assert r['pipeline_run']['status']=='completed_with_warnings'
    stages=r['per_file_results'][0]['stages']
    assert {s['status'] for s in stages}=={'not_configured'}


def test_kd1_detailed_final_report_shows_not_configured_layout_and_mineru(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch); monkeypatch.delenv('PP_DOCLAYOUT_COMMAND', raising=False); monkeypatch.delenv('MINERU_COMMAND', raising=False)
    import app.services.adapters as adapters
    monkeypatch.setattr(adapters, 'post_ollama_chat', lambda base_url, payload, timeout=120.0: fake_ollama_raw())
    r=pipeline.process_pipeline('КД1',[item(pdf(tmp_path/'kd1.pdf'))], tmp_path/'data')
    report=json.loads(Path(r['pipeline_run']['final_report_json_path']).read_text(encoding='utf-8'))
    by_stage={s['stage']:s for s in report['stage_results']}
    assert by_stage['PP-DocLayout-L']['status']=='not_configured'
    assert by_stage['PP-DocLayout-L']['error']=='PP_DOCLAYOUT_COMMAND is not configured'
    assert by_stage['MinerU 2.5']['status']=='not_configured'
    assert by_stage['MinerU 2.5']['error']=='MINERU_COMMAND is not configured'
    assert by_stage['Qwen3-VL-8B']['status']=='completed'
    assert by_stage['Qwen2.5-3B']['status']=='completed'
    md=Path(r['pipeline_run']['final_report_md_path']).read_text(encoding='utf-8')
    assert '## Результаты по этапам' in md
    assert 'PP_DOCLAYOUT_COMMAND is not configured' in md
    assert 'MINERU_COMMAND is not configured' in md
    assert 'Отдельный BOM-файл не загружен и не подтверждён' in md


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


def fake_ollama_raw():
    return {"message":{"content":"{}"},"prompt_eval_count":7,"eval_count":5,"total_duration":100,"load_duration":10,"prompt_eval_duration":20,"eval_duration":30}


def test_pipeline_runs_qwen_when_layout_and_mineru_not_configured(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    monkeypatch.delenv('PP_DOCLAYOUT_COMMAND', raising=False); monkeypatch.delenv('MINERU_COMMAND', raising=False)
    import app.services.adapters as adapters
    monkeypatch.setattr(adapters, 'post_ollama_chat', lambda base_url, payload, timeout=120.0: fake_ollama_raw())
    r=pipeline.process_pipeline('КД1',[item(pdf(tmp_path/'kd1.pdf'))], tmp_path/'data')
    report=json.loads(Path(r['pipeline_run']['final_report_json_path']).read_text(encoding='utf-8'))
    by_stage={s['stage']:s for s in report['stage_results']}
    assert by_stage['PP-DocLayout-L']['status']=='not_configured'
    assert by_stage['MinerU 2.5']['status']=='not_configured'
    assert by_stage['Qwen3-VL-8B']['status']=='completed'
    assert by_stage['Qwen2.5-3B']['status']=='completed'
    assert report['model_results']['qwen3_vl_8b'][0]['source_type']=='изображение'
    assert report['model_results']['qwen2_5_3b']['source_type']=='очищенный JSON'


def test_pipeline_ollama_error_is_failed_not_not_configured(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    import app.services.adapters as adapters
    def boom(base_url, payload, timeout=120.0):
        raise ConnectionError('real ollama error')
    monkeypatch.setattr(adapters, 'post_ollama_chat', boom)
    r=pipeline.process_pipeline('КД1',[item(pdf(tmp_path/'kd1.pdf'))], tmp_path/'data')
    by_stage={s['stage']:s for s in r['stage_results']}
    assert by_stage['Qwen3-VL-8B']['status']=='failed'
    assert by_stage['Qwen2.5-3B']['status']=='failed'
    assert 'real ollama error' in by_stage['Qwen3-VL-8B']['error']


def test_final_report_contains_qwen_tokens_and_times(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    import app.services.adapters as adapters
    monkeypatch.setattr(adapters, 'post_ollama_chat', lambda base_url, payload, timeout=120.0: fake_ollama_raw())
    r=pipeline.process_pipeline('КД1',[item(pdf(tmp_path/'kd1.pdf'))], tmp_path/'data')
    report=json.loads(Path(r['pipeline_run']['final_report_json_path']).read_text(encoding='utf-8'))
    by_stage={s['stage']:s for s in report['stage_results']}
    for name in ['Qwen3-VL-8B','Qwen2.5-3B']:
        assert by_stage[name]['input_text_tokens']==7
        assert by_stage[name]['output_text_tokens']==5
        assert by_stage[name]['total_duration']==100
        assert by_stage[name]['wall_clock_seconds'] is not None
    md=Path(r['pipeline_run']['final_report_md_path']).read_text(encoding='utf-8')
    assert 'Статус сформирован по ограниченному cleaned JSON без результатов MinerU; требует повторной проверки после подключения MinerU' in md
    assert 'Перечень элементов обнаружен в PDF' in md or 'Перечень элементов в PDF не обнаружен' in md
    assert 'Отдельный BOM-файл не загружен и не подтверждён' in md


def test_qwen3_timeout_keeps_qwen25_completed_and_visual_input(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    monkeypatch.setenv('QWEN3_VL_TIMEOUT_SECONDS', '600')
    import app.services.adapters as adapters

    def fake_post(base_url, payload, timeout=120.0):
        if payload['model'] == 'qwen3-vl:8b':
            raise adapters.OllamaResponseTimeoutError(f"Модель была доступна, но не завершила ответ за {timeout:g} секунд")
        return fake_ollama_raw()

    monkeypatch.setattr(adapters, 'post_ollama_chat', fake_post)
    r = pipeline.process_pipeline('КД1', [item(pdf(tmp_path/'kd1.pdf'))], tmp_path/'data')
    report = json.loads(Path(r['pipeline_run']['final_report_json_path']).read_text(encoding='utf-8'))
    by_stage = {s['stage']: s for s in report['stage_results']}

    assert by_stage['Qwen3-VL-8B']['status'] == 'failed'
    assert by_stage['Qwen3-VL-8B']['error_type'] == 'response_timeout'
    assert by_stage['Qwen3-VL-8B']['error'] == 'Модель была доступна, но не завершила ответ за 600 секунд'
    assert by_stage['Qwen3-VL-8B']['visual_input'] == {'image_count': 1, 'width': 144, 'height': 144}
    assert report['model_results']['qwen3_vl_8b'][0]['visual_input'] == {'image_count': 1, 'width': 144, 'height': 144}
    assert by_stage['Qwen2.5-3B']['status'] == 'completed'
