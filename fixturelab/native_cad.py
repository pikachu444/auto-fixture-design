"""Native FreeCAD parameter authoring and CAD validation.

The user picks a feature property or a Sketcher driving dimension. Definitions
live inside the editable FCStd document; no per-model form schema is coded here.
"""
from datetime import datetime,timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile

import cadquery as cq

from .cad import export_and_check,part
from .render import preview

ROOT=Path(__file__).resolve().parents[1]
DESIGNS=ROOT/'artifacts/native_designs'


def _run(request):
    command=os.environ.get('FREECAD_CMD') or shutil.which('freecadcmd') or shutil.which('FreeCADCmd')
    if not command:raise RuntimeError('FreeCADCmd is required; set FREECAD_CMD to its executable')
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/'request.json';result=Path(tmp)/'result.json'
        source.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
        env={**os.environ,'FIXTURE_FREECAD_REQUEST':str(source),'FIXTURE_FREECAD_RESULT':str(result)}
        run=subprocess.run([command,str(ROOT/'fixturelab/freecad_worker.py')],cwd=ROOT,
                           env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=150)
        if not result.exists():raise RuntimeError('FreeCADCmd produced no result: '+(run.stderr or run.stdout)[-1000:])
        answer=json.loads(result.read_text(encoding='utf-8'))
        if not answer['ok']:raise ValueError('FreeCAD: '+answer['error'])
        if run.returncode:raise RuntimeError('FreeCADCmd returned an error')
        return answer['result']


def _path(design):
    if not isinstance(design,str) or not re.fullmatch(r'[a-f0-9]{32}',design):
        raise ValueError('Invalid CAD design id')
    path=DESIGNS/design/'editable.FCStd'
    if not path.is_file():raise ValueError('Native CAD document not found')
    return path


def inspect(design):
    info=_run({'action':'inspect','document':str(_path(design))})
    return {'design':design,**info,'preview':f'/designs/{design}/preview.png',
            'editable':f'/designs/{design}/editable.FCStd'}


def _preview_step(step,target):
    shape=cq.importers.importStep(str(step)).val()
    if len(shape.Solids())!=1 or not shape.isValid() or shape.Volume()<=0:
        raise RuntimeError('FreeCAD did not export one valid solid')
    preview([part('native_preview','printed',shape)],target,fit=True)


def _new_path():
    design=uuid.uuid4().hex
    folder=DESIGNS/design;folder.mkdir(parents=True,exist_ok=False)
    return design,folder/'editable.FCStd'


def create_sample(template='roller_support'):
    if template not in ('roller_support','sketch_locator'):
        raise ValueError('Unknown native CAD template')
    design,path=_new_path()
    _run({'action':'bootstrap' if template=='roller_support' else 'bootstrap_sketch',
          'document':str(path)})
    baseline=path.parent/'baseline'
    baseline.mkdir()
    _run({'action':'generate','document':str(path),'values':{},'output':str(baseline)})
    _preview_step(baseline/'native.step',path.parent/'preview.png')
    return inspect(design)


def import_document(data):
    if len(data)>25*1024*1024 or len(data)<100:raise ValueError('FCStd file size must be 100 bytes to 25 MB')
    with tempfile.TemporaryFile() as memory:
        memory.write(data);memory.seek(0)
        if not zipfile.is_zipfile(memory):raise ValueError('Expected an editable FreeCAD FCStd document')
        memory.seek(0)
        with zipfile.ZipFile(memory) as archive:
            if 'Document.xml' not in archive.namelist():raise ValueError('Missing FreeCAD document history')
    design,path=_new_path();path.write_bytes(data)
    info=inspect(design)
    if info['final']:
        baseline=path.parent/'baseline';baseline.mkdir()
        generated=_run({'action':'generate','document':str(path),'values':{},'output':str(baseline)})
        if generated['decision']=='REVIEW_REQUIRED':_preview_step(baseline/'native.step',path.parent/'preview.png')
    return info


def register(design,target,name,minimum,maximum,label=None):
    if not isinstance(label,(str,type(None))) or (label and len(label)>80):
        raise ValueError('Invalid CAD parameter label')
    return {'design':design,**_run({'action':'register','document':str(_path(design)),
                                   'target':target,'name':name,'min':minimum,'max':maximum,
                                   'label':label or name})}


def select_final(design,final):
    info=_run({'action':'select_final','document':str(_path(design)),'final':final})
    path=_path(design)
    baseline=path.parent/'baseline';baseline.mkdir(exist_ok=True)
    for old in baseline.iterdir():old.unlink()
    generated=_run({'action':'generate','document':str(path),'values':{},'output':str(baseline)})
    if generated['decision']=='REVIEW_REQUIRED':_preview_step(baseline/'native.step',path.parent/'preview.png')
    return {'design':design,**info,'preview':f'/designs/{design}/preview.png'}


def execute(design,values,output):
    source=_path(design)
    if not isinstance(values,dict):raise ValueError('Expected a parameter mapping')
    out=Path(output)
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty')
    out.mkdir(parents=True,exist_ok=True)
    before=inspect(design)
    raw=_run({'action':'generate','document':str(source),'values':values,'output':str(out)})
    result={'design':design,'document':before['document'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'parameters':raw.get('parameters',values),'decision':raw['decision'],
            'production_release':'UNKNOWN','cad_generated':False,
            'checks':raw['checks'],'cad_checks':[],'bom':[],
            'structural_analysis':'NOT_RUN','executed_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'Native CAD feature and sketch dimensions, final BREP and mesh integrity. Machine interface and strength need separate checks.'}
    (out/'input.json').write_text(json.dumps({'design':design,'values':values},ensure_ascii=False,indent=2))
    if raw['decision']=='REVIEW_REQUIRED':
        shape=cq.importers.importStep(str(out/'native.step')).val()
        if len(shape.Solids())!=1 or not shape.isValid() or shape.Volume()<=0:
            raise RuntimeError('Invalid native CAD STEP')
        result['cad_checks'],result['bom']=export_and_check([part('native_printed_part','printed',shape)],out)
        if any(c['status']!='PASS' for c in result['cad_checks']):raise RuntimeError('CAD export integrity checks failed')
        preview([part('native_printed_part','printed',shape)],out/'preview.png',fit=True)
        result['cad_generated']=True
        result['bounds_mm']=result['bom'][0]['bounds_mm']
    result['files']=[x.name for x in out.iterdir() if x.is_file()]+['result.json','report.html']
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    esc=html.escape
    rows=''.join('<tr><td>'+esc(p['name'])+'</td><td>'+esc(str(result['parameters'].get(p['name'])))+
                 ' mm</td><td>'+esc(p['object']+' / '+(p.get('property') or p.get('constraint','')))+
                 '</td></tr>' for p in before['parameters'])
    checks=''.join(f'<li>{esc(c["code"])}: {esc(c["status"])} · {esc(str(c.get("observed","")))}</li>'
                   for c in result['checks']+result['cad_checks'])
    figure='<img src="preview.png" style="max-width:100%" alt="Generated CAD">' if result['cad_generated'] else '<p>조건 위반: CAD 파일을 출력하지 않았습니다.</p>'
    (out/'report.html').write_text(f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>FreeCAD 설계 검증</title>
<style>body{{font:15px system-ui;max-width:1000px;margin:25px auto;padding:0 20px;color:#17364a}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d8e2e9;padding:8px;text-align:left}}</style>
<h1>FreeCAD 원본의 사용자 정의 파라미터</h1><p>판정: {result['decision']} · 제작 승인: UNKNOWN · 강도 해석: NOT_RUN</p>
{figure}<table><tr><th>사용자가 붙인 이름</th><th>입력값</th><th>CAD의 실제 치수</th></tr>{rows}</table>
<h2>검사</h2><ul>{checks}</ul><p>STEP/STL/3MF 무결성은 검사했지만 실제 장비 인터페이스와 재료 강도는 검증하지 않았습니다.</p>
<p><a href="result.json">JSON 판정 근거</a> · <a href="editable.FCStd">재편집 가능한 FreeCAD 문서</a></p></html>''',encoding='utf-8')
    return result
