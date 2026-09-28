from datetime import datetime,timezone
from pathlib import Path
import csv,hashlib,html,importlib.metadata,json,os,platform,subprocess,time
from .core import evaluate

ROOT=Path(__file__).resolve().parents[1]
def provenance(data):
    try:sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except (subprocess.SubprocessError,OSError):sha='unavailable'
    versions={}
    for package in ['cadquery','trimesh','numpy','matplotlib']:
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]='unavailable'
    try:dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip())
    except (subprocess.SubprocessError,OSError):dirty=None
    sources=list((ROOT/'fixturelab').glob('*.py'))+[ROOT/'fixturelab/ui.html',ROOT/'legacy/src/fixture.py']
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}
    return {'executed_utc':datetime.now(timezone.utc).isoformat(),'git_sha':os.environ.get('GITHUB_SHA',sha),'working_tree_dirty':dirty,'source_sha256':source_hashes,'input_sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),'python':platform.python_version(),'libraries':versions,'github_run':os.environ.get('GITHUB_RUN_ID')}

def execute(data,output):
    start=time.monotonic();out=Path(output)
    # Never leave a previous successful CAD beside a new rejected result.
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty; use a new directory for each run')
    result=evaluate(data);out.mkdir(parents=True,exist_ok=True)
    result['provenance']=provenance(data);result['cad_checks']=[];result['bom']=[]
    if result['decision']!='REJECTED':
        from .cad import build,export_and_check
        from .render import preview
        parts=build(result);checks,bom=export_and_check(parts,out)
        result['cad_checks']=checks;result['bom']=bom;result['cad_generated']=True
        # Verify generated geometry against analytical print envelope and roller span.
        q=data['design'];pad=2*(q['brim']+q['edge_margin'])
        for item in bom:
            if item['role']!='printed':continue
            bounds=item['bounds_mm'];occ=[bounds[0]+pad,bounds[1]+pad,bounds[2]]
            checks.append({'code':'measured_print_fit_'+item['part'],'status':'PASS' if all(a<=b+1e-6 for a,b in zip(occ,data['printer']['build'])) else 'FAIL','detail':{'occupied_mm':occ,'build_mm':data['printer']['build']}})
        if data['type']=='bending':
            centers=[p['shape'].Center().x for p in parts if 'metal_roller' in p['name']]
            observed=abs(centers[1]-centers[0]);required=result['metrics']['span_mm']
            checks.append({'code':'measured_roller_spacing','status':'PASS' if abs(observed-required)<1e-6 else 'FAIL','detail':{'measured_mm':observed,'required_mm':required}})
        if any(c['status']=='FAIL' for c in checks):result['decision']='COMPUTATION_ERROR'
        preview(parts,out/'preview.png')
    result['elapsed_seconds']=round(time.monotonic()-start,3)
    result['files']=[p.name for p in sorted(out.iterdir()) if p.is_file()]
    (out/'input.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'bom.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['part','role','quantity','bounds_mm','volume_mm3','print_file']);writer.writeheader();writer.writerows(result['bom'])
    report(result,out)
    if result['decision']=='COMPUTATION_ERROR':raise RuntimeError('CAD verification failed; see '+str(out/'result.json'))
    return result

def report(r,out):
    d=r['input'];lines=[f'# {d["title"]}',f'\n**설계 판정: {r["decision"]} · 제작 승인: UNKNOWN**',f'\n용도: {r["use"]}', '\n계산 결과는 입력값에 따른 예측입니다. 장비의 실측값이나 실험 결과가 아닙니다.', '\n## 계산 결과','\n| 항목 | 값 |','|---|---:|']
    lines += [f'| {k} | {v:.6g} |' if isinstance(v,(int,float)) else f'| {k} | {v} |' for k,v in r['metrics'].items()]
    lines+=['\n## 설계 검사','\n| 검사 | 상태 | 계산/입력 | 한계 | 근거 |','|---|---|---|---|---|']
    lines += [f'| {c["code"]} | {c["status"]} | {c["observed"]} | {c["limit"]} | {c["reason"]} |' for c in r['checks']]
    lines+=['\n## 실제 CAD 검사']+[f'- {c["code"]}: {c["status"]} — {json.dumps(c["detail"],ensure_ascii=False)}' for c in r['cad_checks']]
    if not r['cad_generated']:lines+=['- 설계 제약 위반으로 CAD 내보내기를 중단했습니다.']
    lines+=['\n## 미검증·사용 범위']+['- '+x for x in r['limitations']]
    lines+=['\n## 재현 정보','```json',json.dumps(r['provenance'],ensure_ascii=False,indent=2),'```','\n전체 입력은 input.json, 부품 목록은 bom.csv에 있습니다. STEP은 조립체, STL/3MF는 개별 출력 후보입니다. 3MF에 프린터 프로파일은 없습니다.']
    md='\n'.join(lines);(out/'report.md').write_text(md,encoding='utf-8')
    def esc(v):return html.escape(str(v))
    rows=''.join('<tr>'+''.join('<td>'+esc(c.get(k,''))+'</td>' for k in ['code','status','observed','limit','reason'])+'</tr>' for c in r['checks'])
    cadrows=''.join(f'<tr><td>{esc(c["code"])}</td><td>{esc(c["status"])}</td><td>{esc(c["detail"])}</td></tr>' for c in r['cad_checks'])
    files=' '.join(f'<a href="{esc(name)}">{esc(name)}</a>' for name in r['files'])
    pic='<img src="preview.png" alt="Generated CAD geometry">' if r['cad_generated'] else '<p class="alert">설계 제약 위반: CAD를 생성하지 않았습니다.</p>'
    document=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(d['title'])}</title><style>body{{font:15px system-ui;max-width:1200px;margin:30px auto;padding:0 20px;color:#193447}}h1{{font-size:26px}}.alert{{background:#fff1d6;padding:16px;border-left:4px solid #cc8d24}}table{{border-collapse:collapse;width:100%;font-size:13px;margin:16px 0}}td,th{{padding:9px;border:1px solid #d8e2e9;text-align:left;overflow-wrap:anywhere}}img{{max-width:100%}}a{{display:inline-block;margin:5px;color:#176c8e}}pre{{white-space:pre-wrap;background:#f1f5f7;padding:16px}}@media print{{button{{display:none}}}}</style><h1>{esc(d['title'])}</h1><p class="alert">설계 판정: <b>{r['decision']}</b> · 제작 승인: <b>UNKNOWN</b></p><p>{esc(r['use'])}</p>{pic}<h2>계산 결과</h2><pre>{esc(json.dumps(r['metrics'],ensure_ascii=False,indent=2))}</pre><h2>설계 검사</h2><table><tr><th>검사</th><th>상태</th><th>계산/입력</th><th>한계</th><th>근거</th></tr>{rows}</table><h2>실제 CAD 검사</h2><table>{cadrows}</table><h2>미검증·사용 범위</h2><ul>{''.join('<li>'+esc(x)+'</li>' for x in r['limitations'])}</ul><h2>결과 파일</h2>{files}<h2>재현 정보</h2><pre>{esc(json.dumps(r['provenance'],indent=2))}</pre><details><summary>전체 입력</summary><pre>{esc(json.dumps(d,ensure_ascii=False,indent=2))}</pre></details><p>출처·모델 가정은 저장소 docs/ENGINEERING.md를 확인하세요. 수치는 입력 기반 계산이며 실측 결과가 아닙니다.</p><button onclick="window.print()">보고서 인쇄</button></html>'''
    (out/'report.html').write_text(document,encoding='utf-8')

def run_suite(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cases=json.loads((ROOT/'examples/suite.json').read_text());results=[];failures=0
    for case in cases:
        data=json.loads((ROOT/'examples'/case['file']).read_text())
        try:
            r=execute(data,output/data['id']);passed=r['decision']==case['expected']
            entry={'id':data['id'],'title':data['title'],'expected':case['expected'],'actual':r['decision'],'regression_pass':passed,'cad_generated':r['cad_generated'],'design_failures':[c['code'] for c in r['checks'] if c['status']=='FAIL'],'cad_checks':len(r['cad_checks'])}
        except Exception as exc:
            passed=False;entry={'id':data['id'],'actual':'COMPUTATION_ERROR','regression_pass':False,'error':str(exc)}
        results.append(entry);failures+=int(not passed);print(json.dumps(entry,ensure_ascii=False),flush=True)
    summary={'cases':len(results),'regression_passed':len(results)-failures,'regression_failed':failures,'production_release':'UNKNOWN','results':results}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# Fixture suite execution report',f'\n{len(results)-failures}/{len(results)} regression cases matched expectations. Production release: UNKNOWN.','\nA correctly rejected engineering case is a passing regression test, not an approved fixture.','\n| Case | Expected | Actual | Regression |','|---|---|---|---|']
    md += [f'| {r["id"]} | {r.get("expected", "-")} | {r["actual"]} | {r["regression_pass"]} |' for r in results]
    (output/'SUMMARY.md').write_text('\n'.join(md),encoding='utf-8')
    links=''.join(f'<li><a href="{html.escape(r["id"])}/report.html">{html.escape(r["id"])}</a> — {r["actual"]}</li>' for r in results)
    (output/'index.html').write_text(f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>Fixture CI report</title><style>body{{font:16px system-ui;max-width:1000px;margin:40px auto}}li{{padding:9px}}</style><h1>실험 지그 자동 실행 결과</h1><p>{len(results)-failures}/{len(results)} 회귀 검사 통과. 제작 승인 UNKNOWN.</p><p>REJECTED는 해당 입력의 설계 제약 위반입니다. 예상대로 거부되면 회귀 검사는 통과합니다.</p><ul>{links}</ul></html>',encoding='utf-8')
    manifest={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file() and p.name!='sha256.json'}
    (output/'sha256.json').write_text(json.dumps(manifest,indent=2))
    return int(failures>0)
