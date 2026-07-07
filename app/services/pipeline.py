from __future__ import annotations

import json, os, shutil, subprocess, time, zipfile
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from app.services.pdf_metadata import inspect_pdf
from app.services.normalization import write_json
from app.services.repository import create_run

SUPPORTED={'.pdf','.docx','.xlsx','.xls'}
DATA_DIR=Path('data')

def _now():
    import datetime; return datetime.datetime.utcnow().isoformat(timespec='seconds')+'Z'

def _rel(p:Path): return str(p)

def save_uploads(run_id, uploads, data_dir=DATA_DIR):
    base=data_dir/'input'/run_id; base.mkdir(parents=True, exist_ok=True)
    files=[]
    for up in uploads:
        name=Path(up.filename).name; ext=Path(name).suffix.lower()
        if ext not in SUPPORTED: raise ValueError(f'Unsupported file format: {ext}')
        fid=uuid4().hex; path=base/f'{Path(name).stem}-{fid}{ext}'
        content=up.file.read() if hasattr(up,'file') else up.read()
        if hasattr(content,'__await__'): raise RuntimeError('async upload must be read by route')
        path.write_bytes(content)
        files.append({'id':fid,'original_filename':name,'saved_path':str(path),'extension':ext,'mime_type':getattr(up,'content_type',None),'file_size_bytes':len(content)})
    return files

def inventory_file(f):
    path=Path(f['saved_path']); ext=f['extension']
    out=f|{'detected_document_type':ext.lstrip('.').upper(),'page_count':None,'sheet_count':None,'image_count':None,'table_count':None,'processing_status':'inventoried','error_message':None}
    try:
        if ext=='.pdf':
            m=inspect_pdf(path); out.update(page_count=m['page_count'], image_count=m['image_count'], table_count=None)
        elif ext=='.docx':
            out.update(_inspect_docx(path))
        elif ext in {'.xlsx','.xls'}:
            out.update(_inspect_excel(path))
    except Exception as e:
        out.update(processing_status='inventory_failed', error_message=str(e))
    return out

def _inspect_docx(path):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paras=tables=imgs=0
    with zipfile.ZipFile(path) as z:
        if 'word/document.xml' in z.namelist():
            root=ET.fromstring(z.read('word/document.xml'))
            paras=len(root.findall('.//w:p',ns)); tables=len(root.findall('.//w:tbl',ns))
        imgs=len([n for n in z.namelist() if n.startswith('word/media/')])
    return {'page_count':None,'sheet_count':None,'image_count':imgs,'table_count':tables,'paragraph_count':paras}

def _inspect_excel(path):
    if path.suffix.lower()=='.xlsx':
        with zipfile.ZipFile(path) as z:
            sheets=len([n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')])
            tables=len([n for n in z.namelist() if n.startswith('xl/tables/') and n.endswith('.xml')]) or None
        return {'sheet_count':sheets,'page_count':None,'image_count':None,'table_count':tables}
    return {'sheet_count':None,'page_count':None,'image_count':None,'table_count':None}

def parse_docx(path):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}; sections=[]; tables=[]; images=[]; props={}
    with zipfile.ZipFile(path) as z:
        names=z.namelist(); images=[n for n in names if n.startswith('word/media/')]
        if 'word/document.xml' in names:
            root=ET.fromstring(z.read('word/document.xml'))
            texts=[''.join(t.text or '' for t in p.findall('.//w:t',ns)).strip() for p in root.findall('.//w:p',ns)]
            sections=[t for t in texts if t]
            for tbl in root.findall('.//w:tbl',ns):
                rows=[]
                for tr in tbl.findall('.//w:tr',ns):
                    rows.append([''.join(t.text or '' for t in tc.findall('.//w:t',ns)).strip() for tc in tr.findall('./w:tc',ns)])
                tables.append(rows)
    return {'text_by_sections':sections,'tables':tables,'images':images,'document_names':[],'suspicious_values':[],'source_file':str(path),'properties':props}

def parse_xlsx(path):
    try:
        from openpyxl import load_workbook
    except Exception as e:
        return {'parser_status':'not_configured','error':str(e),'sheets':[]}
    wb=load_workbook(path, data_only=False); wbv=load_workbook(path, data_only=True)
    sheets=[]
    for ws in wb.worksheets:
        wsv=wbv[ws.title]; rows=[]
        for row in ws.iter_rows():
            vals=[]
            for c in row:
                vals.append({'coordinate':c.coordinate,'value':c.value,'formula':c.value if isinstance(c.value,str) and c.value.startswith('=') else None,'formula_value':wsv[c.coordinate].value,'status':'требует проверки' if c.value in (None,'') else 'ok'})
            rows.append(vals)
        sheets.append({'name':ws.title,'max_row':ws.max_row,'max_column':ws.max_column,'merged_cells':[str(r) for r in ws.merged_cells.ranges],'rows':rows,'tables':list(ws.tables.keys())})
    return {'parser_status':'completed','file_name':path.name,'sheets':sheets}

def run_command_stage(cmd, args, raw_dir):
    if not cmd: return {'status':'not_configured','error':'command is not configured'}
    exe=shutil.which(cmd.split()[0])
    if exe is None and not Path(cmd.split()[0]).exists(): return {'status':'not_configured','error':f'command not found: {cmd}'}
    try:
        p=subprocess.run(cmd.split()+args, capture_output=True, text=True, timeout=300)
        return {'status':'completed' if p.returncode==0 else 'failed','returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    except Exception as e: return {'status':'failed','error':str(e)}

def process_pipeline(kit, files, data_dir=DATA_DIR):
    start=time.perf_counter(); pid=uuid4().hex; root=data_dir/'pipeline_runs'/pid; raw=root/'raw'; clean=root/'cleaned'; raw.mkdir(parents=True); clean.mkdir()
    inv=[inventory_file(f|{'pipeline_run_id':pid}) for f in files]
    write_json(root/'file_manifest.json', {'pipeline_run_id':pid,'kit':kit,'files':inv})
    cleaned={'pipeline_run_id':pid,'kit':kit,'uploaded_files':inv,'found_documents':[],'unconfirmed_documents':[],'files':[],'potential_bom_rows':[],'images_and_schemes':[],'suspicious_ocr_fragments':[],'data_quality_risks':[],'raw_outputs':[]}
    warnings=[]
    for f in inv:
        fp=Path(f['saved_path']); ext=f['extension']; fr={'input_file_id':f['id'],'file':f['original_filename'],'stages':[]}
        if f['processing_status'].endswith('failed'): warnings.append(f['original_filename'])
        if ext=='.pdf':
            pp=run_command_stage(os.getenv('PP_DOCLAYOUT_COMMAND',''), [str(fp)], raw); miner=run_command_stage(os.getenv('MINERU_COMMAND',''), [str(fp)], raw)
            for name,res in [('PP-DocLayout-L',pp),('MinerU 2.5',miner)]:
                p=raw/f"{f['id']}-{name.replace(' ','_')}.json"; write_json(p,res); cleaned['raw_outputs'].append(str(p)); fr['stages'].append({'stage':name, **res});
                if res['status']!='completed': warnings.append(f"{f['original_filename']}:{name}:{res['status']}")
                _record_test_run(kit,pid,f,name,res,str(p))
        elif ext=='.docx':
            try:
                res=parse_docx(fp); status='completed'; cleaned['found_documents'].append({'file':f['original_filename'],'type':'DOCX'})
            except Exception as e:
                res={'parser_status':'failed','error':str(e),'source_file':str(fp)}; status='failed'; warnings.append(f['original_filename'])
            p=clean/f"{f['id']}-docx-cleaned.json"; write_json(p,res); fr['cleaned_json_path']=str(p); fr['cleaned_excerpt']=res; fr['stages'].append({'stage':'deterministic-docx','status':status})
        elif ext=='.xlsx':
            res=parse_xlsx(fp); p=clean/f"{f['id']}-xlsx-cleaned.json"; write_json(p,res); fr['cleaned_json_path']=str(p); fr['stages'].append({'stage':'deterministic-excel','status':res.get('parser_status')}); cleaned['found_documents'].append({'file':f['original_filename'],'type':'XLSX'})
        elif ext=='.xls':
            res={'parser_status':'not_configured','error':'XLS parser dependency/command is not configured','sheets':[]}; p=clean/f"{f['id']}-xls-cleaned.json"; write_json(p,res); fr['cleaned_json_path']=str(p); fr['stages'].append({'stage':'deterministic-excel','status':'not_configured'}); warnings.append(f['original_filename'])
        cleaned['files'].append(fr)
    # mentions not confirmation
    text=json.dumps(cleaned, ensure_ascii=False).lower()
    for doc in ['gerber','step','pick&place','bom']:
        if doc in text and not any(doc in uf['original_filename'].lower() for uf in inv): cleaned['unconfirmed_documents'].append(doc)
    cj=clean/'kit_cleaned.json'; write_json(cj, cleaned)
    final={'pipeline_run':{'id':pid,'kit':kit,'status':'completed_with_warnings' if warnings else 'completed','started_at':_now(),'finished_at':_now(),'total_wall_clock_seconds':round(time.perf_counter()-start,3),'error_message':None},'composition':inv,'per_file_results':cleaned['files'],'model_results':{},'metrics':{},'final':{'suitability':'частично пригодно' if warnings else 'пригодно','critical_errors':[],'unconfirmed_documents':cleaned['unconfirmed_documents'],'questions_to_client':[],'short_recommendation':'Проверьте предупреждения и неподтверждённые документы.' if warnings else 'Комплект обработан детерминированно.'}}
    fj=root/'final_report.json'; fm=root/'final_report.md'; write_json(fj, final); fm.write_text(render_md(final), encoding='utf-8')
    final['pipeline_run']['final_report_json_path']=str(fj); final['pipeline_run']['final_report_md_path']=str(fm); write_json(fj, final)
    return final

def _record_test_run(kit,pid,f,stage,res,raw_path):
    create_run({'kit':kit,'stage_model':stage,'file_name':f['original_filename'],'file_count':1,'page_count':f.get('page_count') or 0,'image_count':f.get('image_count'),'table_count':f.get('table_count'),'visual_input':'не использовался','wall_clock_seconds':None,'raw_output_path':raw_path,'normalized_output_path':None,'result':res.get('status'),'critical_errors':0,'provider':'local','model_id':stage,'execution_mode':'local_cpu','source_type':f['extension'],'parent_run_id':None,'pipeline_run_id':pid,'input_file_id':f['id']})

def render_md(r):
    lines=[f"# Итоговый отчёт комплекта {r['pipeline_run']['kit']}", '', f"Статус: {r['pipeline_run']['status']}", '','## Состав комплекта']
    for f in r['composition']: lines.append(f"- {f['original_filename']} ({f['extension']}), страниц: {f.get('page_count')}, листов: {f.get('sheet_count')}, таблиц: {f.get('table_count')}, изображений: {f.get('image_count')}")
    lines += ['','## Итог', f"- Пригодность: {r['final']['suitability']}", f"- Неподтверждённые документы: {', '.join(r['final']['unconfirmed_documents']) or 'нет'}", f"- Рекомендация: {r['final']['short_recommendation']}"]
    return '\n'.join(lines)+'\n'
