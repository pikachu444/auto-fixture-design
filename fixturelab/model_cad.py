"""Generic execution of trusted CadQuery source models with model-owned inputs.

Only repository-local scripts in models/ can run; do not expose an arbitrary
Python upload endpoint. STEP/STL exports do not carry the source parameters.
"""
import ast
from datetime import datetime,timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re

import cadquery as cq
import cadquery.cqgi as cqgi

from .cad import export_and_check,part
from .render import preview

ROOT=Path(__file__).resolve().parents[1]
MODELS=ROOT/'models'


def definition(slug):
    if not isinstance(slug,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,59}',slug):
        raise ValueError('Invalid CAD model name')
    path=MODELS/(slug+'.py')
    if not path.is_file():raise ValueError('CAD model is not registered in models/')
    source=path.read_text(encoding='utf-8')
    syntax=ast.parse(source,filename=str(path))
    assignments=[n.value for n in syntax.body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=='FIXTURE_META' for t in n.targets)]
    if len(assignments)!=1:raise ValueError('CAD source needs one literal FIXTURE_META')
    meta=ast.literal_eval(assignments[0])
    if set(meta)!={'title','description','parameters'} or not isinstance(meta['parameters'],dict):
        raise ValueError('Invalid CAD model metadata')
    model=cqgi.parse(source)
    found=model.metadata.parameters
    if not found or set(meta['parameters'])!=set(found):
        raise ValueError('CAD parameter metadata must match top-level numeric assignments')
    parameters=[]
    for name,p in meta['parameters'].items():
        info=p.copy()
        if set(info)!={'label','unit','min','max'} or info['unit']!='mm':
            raise ValueError(f'Invalid CAD parameter metadata: {name}')
        default=found[name].default_value
        if not (all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
                    for x in (info['min'],default,info['max']))
                and info['min']<=default<=info['max'] and info['min']<info['max']):
            raise ValueError(f'Invalid numeric CAD parameter: {name}')
        parameters.append({'name':name,'default':default,**info})
    return {'id':slug,'title':meta['title'],'description':meta['description'],
            'parameters':parameters,'source_sha256':hashlib.sha256(source.encode()).hexdigest()},model,source


def catalogue():
    return [definition(p.stem)[0] for p in sorted(MODELS.glob('*.py')) if not p.stem.startswith('_')]


def execute(slug,overrides,output):
    info,model,source=definition(slug)
    if not isinstance(overrides,dict) or set(overrides)-{p['name'] for p in info['parameters']}:
        raise ValueError('Unknown CAD parameter or invalid parameter mapping')
    out=Path(output)
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty')
    out.mkdir(parents=True,exist_ok=True)
    parameters={};checks=[]
    for p in info['parameters']:
        name=p['name'];value=overrides.get(name,p['default'])
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
            raise ValueError(f'{name}: finite numeric value required')
        parameters[name]=value
        ok=p['min']<=value<=p['max']
        checks.append({'code':'range_'+name,'status':'PASS' if ok else 'FAIL',
                       'observed':value,'limit':[p['min'],p['max']]})
    result={'model':info['id'],'title':info['title'],'parameters':parameters,
            'source_sha256':info['source_sha256'],'decision':'REVIEW_REQUIRED',
            'production_release':'UNKNOWN','cad_generated':False,'checks':checks,
            'cad_checks':[],'bom':[],'files':[],
            'structural_analysis':'NOT_RUN',
            'executed_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'CAD source parameters and BREP/mesh file integrity; no load rating or installed-machine qualification.'}
    (out/'cad_source.py').write_text(source,encoding='utf-8')
    (out/'input.json').write_text(json.dumps({'model':slug,'parameters':parameters},indent=2),encoding='utf-8')
    if all(c['status']=='PASS' for c in checks):
        built=model.build(parameters)
        if not built.success:
            if isinstance(built.exception,ValueError):
                result['decision']='REJECTED'
                checks.append({'code':'cad_source_relation','status':'FAIL',
                               'observed':str(built.exception),'limit':'Relations in the CAD source'})
            else:raise RuntimeError(f'CAD script failed: {built.exception}')
        else:
            if len(built.results)!=1:raise RuntimeError('CAD source must show exactly one printable part')
            candidate=built.first_result.shape
            shape=candidate.val() if isinstance(candidate,cq.Workplane) else candidate
            if len(shape.Solids())!=1 or not shape.isValid() or shape.Volume()<=0:
                raise RuntimeError('CAD source must produce one valid solid')
            parts=[part(slug,'printed',shape)]
            result['cad_checks'],result['bom']=export_and_check(parts,out)
            if any(c['status']!='PASS' for c in result['cad_checks']):
                result['decision']='COMPUTATION_ERROR'
            else:result['cad_generated']=True
            preview(parts,out/'preview.png',fit=True)
    else:result['decision']='REJECTED'
    result['files']=[x.name for x in sorted(out.iterdir()) if x.is_file()]
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=[f'# {info["title"]}',f'CAD 모델: `{slug}.py` · 판정: **{result["decision"]}** · 제작 승인: **UNKNOWN**',
           f'소스 SHA-256: `{info["source_sha256"]}`','',
           '| 모델 안에서 정의한 파라미터 | 값 | 범위 | 상태 |','|---|---:|---:|---|']
    lines += [f'| {p["label"]} ({p["name"]}) | {parameters[p["name"]]} {p["unit"]} | {p["min"]}–{p["max"]} | {checks[i]["status"]} |'
              for i,p in enumerate(info['parameters'])]
    lines += ['','## CAD 관계·형상 검사']
    lines += [f'- {c["code"]}: {c["status"]} ({c.get("observed",c.get("detail"))})'
              for c in [*checks[len(info['parameters']):],*result['cad_checks']]]
    lines += ['','## 판정 범위','소스에 정의한 치수·관계와 파일 유효성만 확인했습니다. 실측 장비 구성, 출력물 강도, 체결·접촉 및 FEA는 별도 검증이 필요합니다.']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    esc=html.escape
    rows=''.join(f'<tr><td>{esc(p["label"])} ({esc(p["name"])})</td><td>{parameters[p["name"]]} {esc(p["unit"])}</td><td>{p["min"]}–{p["max"]}</td><td>{checks[i]["status"]}</td></tr>'
                 for i,p in enumerate(info['parameters']))
    err=''.join(f'<li>{esc(c["code"])}: {esc(str(c["observed"]))}</li>' for c in checks if c['status']=='FAIL')
    image='<img src="preview.png" alt="실제 CAD 렌더링">' if result['cad_generated'] else '<p>규칙 위반: CAD 파일을 출력하지 않았습니다.</p>'
    output_html=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>{esc(info['title'])}</title>
<style>body{{font:15px system-ui;max-width:1100px;margin:24px auto;padding:0 20px;color:#17364a}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d8e2e9;padding:9px;text-align:left}}img{{width:100%;max-width:900px}}.status{{background:#fff0cb;padding:14px}}a{{color:#146d89}}</style>
<h1>{esc(info['title'])}</h1><p class="status">CAD 판정: {result['decision']} · 제작 승인: UNKNOWN · 해석: NOT_RUN</p>
<p>{esc(info['description'])}</p>{image}<h2>CAD 소스의 파라미터</h2><table><tr><th>항목</th><th>값</th><th>허용 범위</th><th>검사</th></tr>{rows}</table>
<h2>CAD 관계 검사</h2><ul>{err or '<li>관계 검사 통과</li>'}</ul><p>CAD 파일 검사 {sum(x['status']=='PASS' for x in result['cad_checks'])}건 통과 · 실패 {sum(x['status']=='FAIL' for x in result['cad_checks'])}건.</p>
<p>이 결과는 강도 또는 실제 시험기 장착 적합성 승인이 아닙니다.</p>
<a href="cad_source.py">모델 원본</a> · <a href="result.json">판정 근거 JSON</a> · <a href="report.md">Markdown 보고서</a></html>'''
    (out/'report.html').write_text(output_html,encoding='utf-8')
    if result['decision']=='COMPUTATION_ERROR':raise RuntimeError('CAD integrity checks failed')
    return result
