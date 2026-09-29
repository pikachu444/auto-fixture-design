"""Generate an evidence-based design verification PDF from executed suite files."""
import argparse
import json
import os
import tempfile
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from scripts.build_ci_report import font_path

INK=colors.HexColor('#183348')
BLUE=colors.HexColor('#135d7a')
LIGHT=colors.HexColor('#edf4f7')
RULE=colors.HexColor('#d3e0e7')
AMBER=colors.HexColor('#fbedd2')
RED=colors.HexColor('#f8e7e4')


def run(suite:Path,output:Path):
    summary=json.loads((suite/'summary.json').read_text(encoding='utf-8'))
    cases={x['id']:json.loads((suite/x['id']/'result.json').read_text(encoding='utf-8')) for x in summary['results']}
    fe=json.loads((suite/'structural_screen/result.json').read_text(encoding='utf-8'))
    model_summary_path=suite.parent/'models/summary.json'
    model_summary=json.loads(model_summary_path.read_text(encoding='utf-8')) if model_summary_path.is_file() else None
    if model_summary and model_summary['status']!='PASS':raise ValueError('CAD-source model results are incomplete')
    native_path=suite.parent/'native_acceptance/result.json'
    native_summary=json.loads(native_path.read_text(encoding='utf-8')) if native_path.is_file() else None
    if native_summary and native_summary['status']!='PASS':raise ValueError('Native CAD authoring results are incomplete')
    a,b=cases['bend_4mm'],cases['bend_8mm']
    ma,mb=a['metrics'],b['metrics']
    sa,sb=a['input']['specimen'],b['input']['specimen']
    ea,eb=a['input']['equipment'],b['input']['equipment']
    ba=next(x for x in a['bom'] if x['part']=='printed_base')
    bb=next(x for x in b['bom'] if x['part']=='printed_base')
    support=next(x for x in b['bom'] if x['part']=='printed_support_left')
    pad=2*(b['input']['design']['brim']+b['input']['design']['edge_margin'])
    def check(case,code):return next(c for c in case['checks'] if c['code']==code)
    refused=[x for x in summary['results'] if cases[x['id']]['decision']=='REJECTED']
    generated=[x for x in summary['results'] if cases[x['id']]['cad_generated']]
    if not (summary['cases']==11 and summary['regression_failed']==0 and len(generated)==5
            and len(refused)==6 and all(x['specimen_hand_check']['status']=='MATCH' for x in cases.values())
            and fe['status']=='PRELIMINARY_ONLY_NOT_QUALIFIED' and len(fe['mesh_studies'])==3):
        raise ValueError('Execution evidence is incomplete or changed')
    output.parent.mkdir(parents=True,exist_ok=True)
    W=A4[0]-36*mm
    with tempfile.TemporaryDirectory() as tmp:
        pdfmetrics.registerFont(TTFont('KoreanVerification',str(font_path(Path(tmp)))))
        body=ParagraphStyle('body',fontName='KoreanVerification',fontSize=8.6,leading=13,wordWrap='CJK',textColor=INK,spaceAfter=6)
        small=ParagraphStyle('small',parent=body,fontSize=7.6,leading=11,spaceAfter=3)
        tiny=ParagraphStyle('tiny',parent=body,fontSize=7,leading=10,spaceAfter=2)
        title=ParagraphStyle('title',parent=body,fontSize=19,leading=27,textColor=INK,spaceAfter=12)
        heading=ParagraphStyle('heading',parent=body,fontSize=12,leading=18,textColor=BLUE,spaceBefore=12,spaceAfter=7)
        white=ParagraphStyle('white',parent=small,textColor=colors.white,spaceAfter=0)
        def p(value,style=body):return Paragraph(str(value),style)
        def grid(headers,rows,widths,style=tiny):
            t=Table([[p(h,white) for h in headers]]+[[p(str(v),style) for v in row] for row in rows],
                    colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,-1),(-1,-1),.4,RULE),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            return t
        def box(label,message,bg):
            t=Table([[p(label,heading),p(message,body)]],colWidths=[W*.27,W*.73])
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),bg),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
            return t
        def page(label):story.extend([PageBreak(),p(label,title)])
        def section(label):story.append(p(label,heading))
        run_id=os.environ.get('GITHUB_RUN_ID') or b['provenance'].get('github_run') or 'unknown'
        sha=os.environ.get('GITHUB_SHA') or b['provenance']['git_sha']
        doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,
            topMargin=18*mm,bottomMargin=19*mm,title='실험 지그 설계 검증 보고서 - 3점 굽힘')
        story=[p('설계 검증 보고서 | 3점 굽힘 지그',title),
               box('제작 승인 보류','규칙 및 CAD 검사는 실행됐습니다. 실제 장비 인터페이스, 출력물 강도, 체결·접촉, 해석 수렴과 실물 시험은 미검증입니다.',AMBER),
               Spacer(1,8),grid(['관리 항목','실행 근거'],[
                ('대상','bend_4mm와 bend_8mm의 독립 입력 비교. 구조해석은 bend_8mm 출력 지지대 1개.'),
                ('수량·상태',f'회귀 {summary["regression_passed"]}/{summary["cases"]} 일치 · CAD 생성 {len(generated)}건 · 조건 위반으로 출력 차단 {len(refused)}건 · 제작 승인 UNKNOWN'),
                ('입력 품질','시편 물성·장비 정격·출력 소재 방향 물성은 예제 값 또는 가정값'),
                ('추적 정보',f'Actions {run_id} · 소스 {sha[:12]} · 상세 결과 suite/ 디렉터리')
               ],[W*.23,W*.77])]
        section('01 · 두 입력의 파라미터와 생성 형상 비교')
        story.append(p('두 사례는 별도 예제입니다. 사용자가 두께·길이를 지정했고 프로그램이 고정 템플릿에서 간격과 베이스를 계산했습니다. 기존 CAD를 읽거나 자동 최적화를 수행한 결과가 아닙니다.',small))
        pictures=[]
        for case in (a,b):
            item=case['metrics'];sample=case['input']['specimen']
            caption=f'{sample["thickness"]:g} mm 입력 · {item["span_mm"]:g} mm 간격 · {item["base_length_mm"]:g} mm 베이스'
            pictures.append([Image(str(suite/case['input']['id']/'preview.png'),width=W*.45,height=W*.45*560/1100),p(caption,small)])
        panels=Table([[pictures[0],pictures[1]]],colWidths=[W/2,W/2]);panels.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(panels)
        story.append(grid(['변수·산출값','4 mm 사례','8 mm 사례','변경 근거'],[
            ('시편 두께 / 길이',f'{sa["thickness"]:g} / {sa["length"]:g} mm',f'{sb["thickness"]:g} / {sb["length"]:g} mm','사용자 입력값'),
            ('지지 간격',f'{ma["span_mm"]:g} mm',f'{mb["span_mm"]:g} mm',f'두께 × {sb["span_ratio"]:g}'),
            ('베이스 / X 점유',f'{ba["bounds_mm"][0]:g} / {ba["bounds_mm"][0]+pad:g} mm',f'{bb["bounds_mm"][0]:g} / {bb["bounds_mm"][0]+pad:g} mm','고정 길이 템플릿 선택'),
            ('설계 요구 하중',f'{ma["design_load_N"]:.2f} N',f'{mb["design_load_N"]:.2f} N',f'명목 하중 × {b["input"]["design"]["load_factor"]:g}'),
            ('목표 처짐',f'{ma["deflection_mm"]:.3f} mm',f'{mb["deflection_mm"]:.3f} mm','단순보 근사식')
        ],[W*.30,W*.18,W*.18,W*.34]))
        support_size=' × '.join(f'{v:g}' for v in support['bounds_mm'])
        story.append(p(f'X 점유 = 베이스 길이 + 2 × (브림 {b["input"]["design"]["brim"]:g} mm + 여유 {b["input"]["design"]["edge_margin"]:g} mm). 8 mm 사례의 지지대 외곽은 {support_size} mm입니다.',tiny))

        page('02 · 요구사항 → 계산 → 증거 → 판정')
        story.append(p('판정 대상 bend_8mm. PASS는 해당 소프트웨어 규칙 또는 CAD 검사에 한정됩니다. 실제 시험기 사용 승인이 아닙니다.',small))
        m=mb;s=sb;e=eb;pr=b['input']['printer']['build']
        req=[
          ('형상',f'{check(b,"span_template")["limit"]} mm 템플릿 간격',f'{m["span_mm"]:g} mm','PASS','span_template'),
          ('형상','양쪽 8 mm 시편 여유',f'길이 {s["length"]:g} ≥ {check(b,"specimen_overhang")["limit"]:g} mm','PASS','specimen_overhang'),
          ('형상',f'폭 {check(b,"roller_contact_width")["limit"]:g} mm 이하',f'{s["width"]:g} mm','PASS','roller_contact_width'),
          ('시험기','프레임 정격',f'{m["design_load_N"]:.2f} ≤ {e["frame_capacity"]:,.0f} N','PASS*','frame_capacity'),
          ('시험기','로드셀·공구 각각의 정격',f'{m["design_load_N"]:.2f} ≤ {e["load_cell_capacity"]:,.0f} / {e["tool_capacity"]:,.0f} N','PASS*','load_cell_capacity / tool_capacity'),
          ('시험기','설치 후 가용 이동량',f'{m["deflection_mm"]:.3f} ≤ {e["usable_travel"]:g} mm','PASS*','usable_travel'),
          ('프린터','X 출력 범위 / 브림 포함',f'{bb["bounds_mm"][0]+pad:g} ≤ {pr[0]:g} mm','PASS*','base_printer_fit'),
          ('CAD','STEP, STL/3MF, 솔리드·간섭',f'{len(b["cad_checks"])}개 검사, 실패 0개','PASS','cad_checks / BOM'),
          ('CAD','롤러 중심 거리',f'{m["span_mm"]:g} mm','PASS','measured_roller_spacing'),
          ('수계산','시편 산술 독립 재계산',f'{len(b["specimen_hand_check"]["checked_metrics"])}개 값 일치','MATCH','specimen_hand_check'),
          ('강도','출력 방향별 허용강도·안전율','허용값 없음','미판정','미확보'),
          ('장착','장비 어댑터·볼트·베이스','실측·상세 설계 없음','미판정','미확보')]
        story.append(grid(['영역','기준','관찰값','상태','증거 필드'],req,[W*.13,W*.29,W*.29,W*.11,W*.18]))
        story.extend([Spacer(1,10),box('판정 범위','PASS*는 예제 JSON의 정격·가용 이동량·프린터 범위가 실제 설치 구성과 일치한다는 가정에서만 성립합니다.',LIGHT)])
        section('재현 경로')
        story.append(p('suite/bend_8mm/input.json → result.json(checks, cad_checks, specimen_hand_check) → assembly.step, 출력 부품 STL/3MF, preview.png. 자료는 해당 GitHub Actions 아티팩트에 있습니다.',small))

        page('03 · 규칙 위반 사례의 CAD 출력 차단')
        story.append(p('아래 여섯 건은 REJECTED이며 STEP, STL, 3MF를 내보내지 않았습니다. 차단은 규칙 기반이고 대체 설계를 자동 생성하지 않습니다.',small))
        def failure_detail(cid,r):
            c=lambda code:check(r,code)
            if cid=='bend_span_reject':return f'간격 {c("span_template")["observed"]:g} > 템플릿 {c("span_template")["limit"][1]:g} mm'
            if cid=='bend_load_reject':return f'요구 {r["metrics"]["design_load_N"]:,.2f} > 로드셀 {c("load_cell_capacity")["limit"]:,.0f} / 공구 {c("tool_capacity")["limit"]:,.0f} N'
            if cid=='bend_printer_reject':return f'브림 포함 {min(c("base_printer_fit")["observed"]):g} > 프린터 X {c("base_printer_fit")["limit"]:g} mm'
            if cid=='film_travel_reject':return f'필요 이동 {c("usable_travel")["observed"]:g} > 가용 {c("usable_travel")["limit"]:g} mm'
            if cid=='foam_platen_reject':return (f'압축판 {c("platen_width")["observed"]:g} × {c("platen_length")["observed"]:g} > '
                   f'{c("platen_width")["limit"]:g} × {c("platen_length")["limit"]:g} mm; 하중 {r["metrics"]["design_load_N"]:,.0f} > '
                   f'로드셀 {c("load_cell_capacity")["limit"]:,.0f} / 공구 {c("tool_capacity")["limit"]:,.0f} N')
            if cid=='fold_strain_reject':return f'표면 변형률 {100*c("strain_limit")["observed"]:.3f}% > 허용 {100*c("strain_limit")["limit"]:.3f}%'
            raise ValueError(f'Unknown rejection case: {cid}')
        rows=[]
        for item in refused:
            r=cases[item['id']]
            rows.append((item['id'],failure_detail(item['id'],r),', '.join(c['code'] for c in r['checks'] if c['status']=='FAIL'),'REJECTED<br/>CAD 없음'))
        story.append(grid(['사례','초과된 조건','실패 규칙','실행'],rows,[W*.22,W*.37,W*.27,W*.14]))
        section('CAD를 생성한 사례도 용도가 다릅니다')
        story.append(grid(['실험','생성물','하중 시험 시 적용 범위'],[
          ('3점 굽힘','출력 베이스·지지대와 금속 부품 개념','하중 전달 지그 개념; 강도·체결 검증 전 사용 보류'),
          ('필름 인장','정렬 트레이','벤치 정렬 보조; 금속 그립 장착 후 제거'),
          ('폼 압축','탈착식 코너 결정구','금속판 위에서 위치 맞춘 뒤 하중 전 제거'),
          ('접힘','정적 반경 확인구','정적 표면 변형률 규모만 확인; 피로 장치 아님')
        ],[W*.18,W*.32,W*.50]))
        story.append(p('회귀 11/11은 예상 판정의 재현성입니다. 5건의 CAD 생성도 실제 적합성 승인을 뜻하지 않습니다.',small))

        page('04 · 수계산과 3D 구조해석')
        story.append(p('해석 대상: bend_8mm 출력 지지대 한 개. STEP → Gmsh C3D10 → CalculiX 선형 정적. 베이스·볼트·금속 롤러 및 시험기는 포함되지 않습니다.',small))
        h=fe['analytical_scale_check'];fine=fe['mesh_studies'][-1]
        story.append(grid(['수계산 항목','가정·근거','값'],[
          ('시편 명목 강도 대응 하중',f'단순지지 보·사각 단면; 폭 {s["width"]:g} / 두께 {s["thickness"]:g} / 간격 {m["span_mm"]:g} mm; 강도 입력 {s["strength"]:g} MPa',f'{h["nominal_strength_specimen_load_N"]:.2f} N'),
          ('설계하중 / 지지대당',f'명목 하중 × {b["input"]["design"]["load_factor"]:g} / 2분할',f'{h["design_total_load_N"]:.2f} / {h["load_per_support_N"]:.2f} N'),
          ('명목 평균 압축응력',f'{h["load_per_support_N"]:.2f} N / 외곽 {support["bounds_mm"][0]:g} × {support["bounds_mm"][1]:g} mm²',f'{h["nominal_gross_compressive_stress_MPa"]:.4f} MPa'),
          ('균일 축압축 변위',f'P × 높이 {support["bounds_mm"][2]:g} / (E3 {fe["material"]["E_3_MPa"]:g} MPa × {h["gross_support_area_mm2"]:,.0f} mm²)',f'{h["ideal_uniform_axial_shortening_mm"]:.5f} mm')
        ],[W*.27,W*.51,W*.22]))
        section('메쉬 크기별 실제 계산')
        story.append(grid(['최대 요소 크기','C3D10 요소','절점','받침부 최대 |Uz|','절점 평균 응력 최대'],[
          (f'{x["mesh_size_max_mm"]:.0f} mm',f'{x["elements_C3D10"]:,}',f'{x["nodes"]:,}',
           f'{x["displacement"]["max_abs_vertical_displacement_mm"]:.5f} mm',
           f'{x["stress_diagnostic"]["max_averaged_nodal_von_mises_MPa"]:.3f} MPa') for x in fe['mesh_studies']
        ],[W*.18,W*.18,W*.12,W*.25,W*.27]))
        story.extend([Spacer(1,10),box('수렴 미확인',
            f'3 → 2 mm 변위 차이 {fe["displacement_mesh_change_ratio_last_two"]*100:.2f}%. 최대 응력도 메쉬에 따라 변합니다. 수렴 또는 강도 안전율을 선언할 수 없습니다.',RED)])
        section('해석 조건과 숫자의 의미')
        story.append(p(f'2 mm 해석 변위 {fine["displacement"]["max_abs_vertical_displacement_mm"]:.5f} / 균일 축변위 {h["ideal_uniform_axial_shortening_mm"]:.5f} = {fe["fea_to_idealized_axial_displacement_ratio"]:.2f}배. 하중 도입·기하 모델이 달라 일치 기준으로 쓰지 않습니다. 명목 평균 압축응력과 국부 절점 평균 von Mises 최대값도 직접적인 합격 비교 대상이 아닙니다.',small))
        story.append(p(f'CAD Z 방향 E3={fe["material"]["E_3_MPa"]:g} MPa 등 직교이방성 값은 측정하지 않았습니다. 지지대 아래면 완전 고정, 롤러 안장 부근 절점에 균등 하중. 실제 접촉, 체결 예압, 적층 간 파손·인필, 베이스 유연성은 빠져 있습니다.',small))
        story.append(p('자료: suite/structural_screen/result.json, printed_support_left.step, support_0~2의 gmsh.inp 및 CalculiX deck·dat·frd·로그.',tiny))

        page('05 · 미결 검증과 실제 사용자 화면')
        story.append(grid(['제작 전 검증 과제','필요한 입력·시험 증거','현재 상태'],[
          ('실제 시험기 구성','모델·로드셀·공구 정격, 설치 후 스트로크, 장착 도면·실측','미확보'),
          ('출력물 재료','출력 조건과 방향별 탄성·강도·층간 물성, 허용값','가정값만 있음'),
          ('조립체 강도','베이스·볼트·롤러 접촉/체결, 메쉬 수렴, 허용값 비교','미실행'),
          ('제작 적합성','선택 프린터·슬라이서 프로파일, 실제 치수·홀·조립 검사','미실행'),
          ('실물 시험','단계 하중과 재현성, 손상 검사, 명시적 승인 기준','미실행')
        ],[W*.22,W*.62,W*.16]))
        section('현재 화면의 기능 범위')
        story.append(grid(['기능','구현','실제 동작'],[
          ('예제 선택·숫자 변경','가능','브라우저 입력 폼에서 시편·장비·프린터 값 수정'),
          ('CAD 소스 파라미터 발견','가능' if model_summary else '별도 실행','CadQuery 소스의 숫자 선언과 메타데이터를 읽어 입력 폼 구성'),
          ('CAD 피처 치수 선택·정의','가능' if native_summary else '별도 실행','FreeCAD 피처 길이·반경 또는 Sketcher 구동 치수 선택 후 이름·범위 지정'),
          ('CAD·규칙 재실행','가능','새 STEP/STL/3MF, 정적 PNG, HTML 보고서와 ZIP'),
          ('3D 면 클릭·임의 STEP 재파라미터화','없음','피처 트리와 구속을 사용; 3D 그림은 정적 미리보기'),
          ('화면에서 FEA 실행·응력 보기','없음','굽힘 1건의 FEA는 별도 CLI와 CI에서 실행'),
          ('자동 설계 개선/최적화','없음','템플릿 선택과 규칙 차단만 구현')
        ],[W*.29,W*.12,W*.59]))
        section('추적 가능한 자료')
        story.append(p(f'저장소: https://github.com/pikachu444/auto-fixture-design<br/>실행: https://github.com/pikachu444/auto-fixture-design/actions/runs/{run_id}',small))
        story.append(p('입력: examples/bend_4mm.json, bend_8mm.json, printed_material_ASSUMED.json. 검사 코드: fixturelab/core.py, pipeline.py, handcheck.py, scripts/run_structural_screen.py. 원자료: Actions 아티팩트의 suite/ 폴더.',small))
        story.append(box('최종 판정','규칙과 CAD 생성의 자동화 시연 완료. 실제 3D 프린터 제작 및 시험기 하중 시험을 위한 설계 승인은 보류.',AMBER))

        if model_summary:
            page('06 · CAD 소스에서 정의한 파라미터 변경')
            story.append(p('다음 두 모델의 치수 선언과 허용 범위는 models/의 CadQuery 파일 내부에 있습니다. 프로그램의 CAD 파라미터 화면은 CQGI가 소스에서 발견한 숫자 입력에 따라 구성됩니다. 두 모델은 서로 다른 변수 목록을 사용합니다.',small))
            variants=model_summary['variants']
            pictures=[]
            for slug,caption in (('roller_default','롤러 지지대 · 폭 32 mm'),('roller_wider','롤러 지지대 · 폭 38 mm')):
                pictures.append([Image(str(suite.parent/'models'/slug/'preview.png'),width=W*.45,height=W*.45*560/1100),p(caption,small)])
            pair=Table([[pictures[0],pictures[1]]],colWidths=[W/2,W/2]);pair.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(pair)
            section('CAD 파일 → 값 변경 → 실제 형상 검증')
            story.append(grid(['CAD 소스 / 실험','모델의 입력값','실제 STEP 치수·검사'],[
              ('models/roller_support.py · 원본','support_width_mm = 32',f'{variants["roller_default"]["bounds_mm"]} mm · CAD 검사 {variants["roller_default"]["cad_checks_passed"]}건'),
              ('models/roller_support.py · 수정','support_width_mm = 38',f'{variants["roller_wider"]["bounds_mm"]} mm · CAD 검사 {variants["roller_wider"]["cad_checks_passed"]}건'),
              ('models/film_tray.py · 수정','specimen_width_mm = 20',f'{variants["film_wider"]["bounds_mm"]} mm · CAD 검사 {variants["film_wider"]["cad_checks_passed"]}건'),
              ('models/roller_support.py · 차단','bolt_pitch_x_mm = 30','모델 관계식 위반 · REJECTED · CAD 없음')
            ],[W*.37,W*.26,W*.37]))
            story.append(Spacer(1,9))
            story.append(box('적용 범위','새 CadQuery 소스 모델을 models/에 넣으면 동일 실행기가 입력을 읽습니다. 원본 스크립트의 코드 자체는 신뢰할 수 있어야 합니다. STEP 파일만으로 파라미터 이력은 복원되지 않으며, 이 지지대의 강도 FEA는 아직 연결하지 않았습니다.',LIGHT))
            story.append(p('실행 증거: artifacts/models/summary.json과 각 변형의 cad_source.py, result.json, assembly.step, STL/3MF, preview.png. 이 경로는 앞의 11개 실험 규칙 사례와 별도로 실행합니다.',small))

        if native_summary:
            page('07 · CAD 형상 치수를 사용자가 선택해 정의')
            story.append(p('편집 가능한 FreeCAD 문서에는 시작할 때 노출된 사용자 파라미터가 0개입니다. 실행 중 형상 트리에서 치수 세 개를 사용자가 선택해 이름·범위를 붙인 뒤 같은 FCStd 파일에 저장했습니다. 정의를 추가해도 형상 생성 코드는 바뀌지 않습니다.',small))
            story.append(Image(str(suite.parent/'native_acceptance/changed/preview.png'),width=W*.76,height=W*.76*560/1100))
            section('선택한 CAD 요소 → 원본 문서 → 재생성')
            story.append(grid(['형상 트리에서 고른 치수','사용자가 정의한 이름','실제 출력 근거'],[
              ('SupportBlock.Length','my_support_width','32 → 38 mm; STEP 외곽 X = 38 mm'),
              ('RollerCradle.Radius','selected_cradle_radius','4.15 → 5 mm; 홈 재계산'),
              ('BoltBore1.Radius','selected_bore_radius','2.25 → 5 mm이면 외곽 여유 < 2 mm; REJECTED, STEP 없음')
            ],[W*.32,W*.30,W*.38]))
            story.append(Spacer(1,10))
            story.append(box('확인 결과',f'원본 폭 {native_summary["original_bounds_mm"][0]:g} → 변경 폭 {native_summary["changed_bounds_mm"][0]:g} mm. CAD 파일 무결성 {native_summary["change_cad_checks_passed"]}건 통과. 저장한 FCStd를 다시 열어 사용자 정의 {native_summary["reopened_definition_count"]}개 확인.',LIGHT))
            story.append(p('한계: Feature 속성과 Sketcher의 구동 치수가 있어야 선택할 수 있습니다. 임의 STEP 면 클릭만으로 설계 이력을 복원할 수는 없습니다. 이 모델의 실제 시험기 체결과 출력물 강도는 미검증입니다.',small))
            story.append(p('원자료: native_acceptance/result.json, changed/editable.FCStd, native.step, assembly.step, STL/3MF 및 blocked/result.json.',tiny))

        def footer(canvas,document):
            canvas.saveState();canvas.setStrokeColor(RULE);canvas.line(18*mm,15*mm,A4[0]-18*mm,15*mm)
            canvas.setFont('KoreanVerification',7.5);canvas.setFillColor(INK)
            canvas.drawString(18*mm,10*mm,'Auto Fixture Design | 입력 기반 설계 검증 기록')
            canvas.drawRightString(A4[0]-18*mm,10*mm,str(document.page));canvas.restoreState()
        doc.build(story,onFirstPage=footer,onLaterPages=footer)
    from pypdf import PdfReader
    reader=PdfReader(str(output));full='\n'.join(x.extract_text() or '' for x in reader.pages)
    for phrase in ('제작 승인 보류','수렴 미확인','자동 설계 개선/최적화','bend_load_reject'):
        if phrase not in full:raise RuntimeError(f'PDF is missing {phrase}')
    if len(reader.pages)<(7 if native_summary else 6 if model_summary else 5):raise RuntimeError('Report sections are missing')
    print(f'Design verification report generated: {output} ({len(reader.pages)} pages)')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--suite',type=Path,default=Path('artifacts/suite'))
    parser.add_argument('--output',type=Path,default=Path('artifacts/suite/DESIGN_VERIFICATION.pdf'))
    args=parser.parse_args();run(args.suite,args.output)
