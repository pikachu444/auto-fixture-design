"""Build one readable PDF from the measured outputs of fixturelab suite.

CI uses the OFL licensed NanumGothic font installed by the workflow. A local
PyMuPDF font fallback supports this workspace when Nanum is not installed.
"""
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

NAVY=colors.HexColor('#173b54')
PALE=colors.HexColor('#edf4f7')

def font_path(directory):
    candidates=[Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'),
                Path('C:/Windows/Fonts/malgun.ttf')]
    for path in candidates:
        if path.is_file():return path
    try:
        import fitz
        path=directory/'fallback_korean.ttf'
        path.write_bytes(fitz.Font('korea').buffer)
        return path
    except (ImportError,RuntimeError) as exc:
        raise RuntimeError('Install a Korean TrueType font such as fonts-nanum') from exc

def run(suite:Path,output:Path):
    cases=json.loads((suite/'summary.json').read_text(encoding='utf-8'))
    reports={item['id']:json.loads((suite/item['id']/'result.json').read_text(encoding='utf-8')) for item in cases['results']}
    failures=sum(c['status']=='FAIL' for r in reports.values() for c in r['cad_checks'])
    valid=[x for x in cases['results'] if reports[x['id']]['cad_generated']]
    refused=[x for x in cases['results'] if reports[x['id']]['decision']=='REJECTED']
    assert cases['cases']==len(reports) and cases['regression_failed']==0 and not failures
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        pdfmetrics.registerFont(TTFont('KoreanReport',str(font_path(Path(directory)))))
        regular=ParagraphStyle('body',fontName='KoreanReport',fontSize=9,leading=14,wordWrap='CJK',spaceAfter=8)
        small=ParagraphStyle('small',parent=regular,fontSize=7.7,leading=11,spaceAfter=0)
        header=ParagraphStyle('header',parent=regular,fontSize=18,leading=25,textColor=NAVY,spaceAfter=14)
        subtitle=ParagraphStyle('subtitle',parent=regular,fontSize=10.5,leading=16,textColor=NAVY,spaceBefore=12)
        white=ParagraphStyle('white',parent=small,textColor=colors.white)
        def text(value,style=regular):return Paragraph(str(value),style)
        def grid(labels,rows,widths):
            table=Table([[text(label,white) for label in labels]]+[[text(value,small) for value in row] for row in rows],colWidths=widths,repeatRows=1)
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
            return table
        doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=19*mm,rightMargin=19*mm,topMargin=17*mm,bottomMargin=20*mm,title='자동 지그 설계 실제 실행 보고서')
        W=A4[0]-38*mm
        story=[text('자동 지그 설계 - 실제 실행 결과',header),
               text(f'GitHub Actions: {cases["regression_passed"]}/{cases["cases"]}개 사례가 예상 판정과 일치 · 생성 {len(valid)}건 · 거부 {len(refused)}건'),
               text('정상 사례는 CAD를 생성했고 제약을 위반한 사례에서는 생성하지 않았습니다. 출력과 물성 수치는 예제 입력에 따른 계산값입니다.'),
               text('실제로 생성한 CAD와 수치',subtitle)]
        rows=[]
        def fmt(value,unit=''):return f'{value:,.3f}'.rstrip('0').rstrip('.')+unit
        for row in valid:
            k=row['id'];r=reports[k];m=r['metrics'];s=r['input']['specimen']
            if k.startswith('bend_'):
                detail=f'두께 {fmt(s["thickness"]," mm")}, 지지 간격 {fmt(m["span_mm"]," mm")}; 베이스 {fmt(m["base_length_mm"]," mm")}'
                result=f'설계 요구 하중 {fmt(m["design_load_N"]," N")} / 시편 처짐 {fmt(m["deflection_mm"]," mm")}'
            elif k=='film_alignment':
                detail=f'시편 {fmt(s["width"]," mm")} x {fmt(s["thickness"]," mm")}; 트레이 홈 {fmt(m["channel_width_mm"]," mm")}'
                result=f'하중 {fmt(m["design_load_N"]," N")} / 이동량 {fmt(m["elongation_estimate_mm"]," mm")}'
            elif k=='foam_locator':
                detail=f'시편 {fmt(s["width"]," mm")} x {fmt(s["length"]," mm")}; 위치 결정구 2개'
                result=f'하중 {fmt(m["design_load_N"]," N")} / 이동량 {fmt(m["compression_mm"]," mm")}'
            else:
                detail=f'두께 {fmt(s["thickness"]," mm")}, 안쪽 반경 R{fmt(s["inner_radius"]," mm")}'
                result=f'표면 변형률 {fmt(m["outer_fiber_strain"]*100,"%")}; 허용 {fmt(s["allowable_strain"]*100,"%")}'
            rows.append((k,detail,result))
        story.append(grid(['사례','CAD에 반영한 시편과 지그 치수','입력 기반 계산'],rows,[W*.22,W*.42,W*.36]))
        story.append(text('생성 CAD 미리보기',subtitle))
        thumbnails=[]
        for k in ['bend_8mm','film_alignment','foam_locator','fold_radius_former']:
            image=Image(str(suite/k/'preview.png'),width=76*mm,height=76*mm*560/1100)
            thumbnails.append([image,text(k,small)])
        tiles=Table([thumbnails[:2],thumbnails[2:]],colWidths=[W/2,W/2],rowHeights=[55*mm,55*mm])
        tiles.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3*mm),('TOPPADDING',(0,0),(-1,-1),3*mm)]));story.append(tiles)
        story.append(PageBreak())
        story.extend([text('거부 사례와 그 이유',header),text('예상대로 거부한 경우는 회귀 테스트 성공입니다. 해당 사례의 보고서는 남기고 STEP, STL, 3MF는 내보내지 않았습니다.')])
        reasons=[]
        explain={'span_template':'지그 최대 간격','load_cell_capacity':'로드셀 정격','tool_capacity':'공구 정격','base_printer_fit':'프린터 X 출력 범위','usable_travel':'장착 후 가용 이동량','platen_width':'압축판 폭','platen_length':'압축판 길이','strain_limit':'허용 표면 변형률'}
        for row in refused:
            r=reports[row['id']];issues=[explain.get(c['code'],c['code']) for c in r['checks'] if c['status']=='FAIL']
            m=r['metrics'];k=row['id']
            observed={
                'bend_span_reject':lambda:f'지지 간격 {fmt(m["span_mm"]," mm")} > 160 mm',
                'bend_load_reject':lambda:f'요구 하중 {fmt(m["design_load_N"]," N")} > 500 N',
                'bend_printer_reject':lambda:'브림 포함 베이스 238 mm > 프린터 220 mm',
                'film_travel_reject':lambda:f'필요 이동량 {fmt(m["elongation_estimate_mm"]," mm")} > 40 mm',
                'foam_platen_reject':lambda:f'압축판 110 x 110 mm > 100 x 100 mm; 하중 {fmt(m["design_load_N"]," N")}',
                'fold_strain_reject':lambda:f'표면 변형률 {fmt(m["outer_fiber_strain"]*100,"%")} > 1%',
            }[k]()
            reasons.append((k,observed,', '.join(issues)))
        story.append(grid(['거부한 사례','측정/계산된 입력','실패한 제한'],reasons,[W*.23,W*.43,W*.34]))
        run_id=os.environ.get('GITHUB_RUN_ID')
        run_url=f'https://github.com/pikachu444/auto-fixture-design/actions/runs/{run_id}' if run_id else 'https://github.com/pikachu444/auto-fixture-design/actions/workflows/fixture-ci.yml'
        story.extend([text('검증의 실제 범위',subtitle),
                      text('정상 사례의 OpenCascade 솔리드 유효성, STEP 재읽기, STL/3MF 메시 밀폐성 및 치수/체적, 초기 위치 간섭, 출력 부품의 베드 범위를 검사했습니다. 굽힘 지그에서는 슬롯 전체 조절 범위의 볼트 여유, 볼트와 지지대 간섭, 롤러·시편·상부 노즈의 접촉 위치도 CAD에서 검사했습니다. CAD 검사에서 실패한 항목은 0개입니다.'),
                      ])
        structural=suite/'structural_screen/result.json'
        if structural.is_file():
            fe=json.loads(structural.read_text(encoding='utf-8'))
            coarse,fine=fe['mesh_studies']
            story.extend([text('굽힘 출력 지지대 3D 유한요소 예비해석',subtitle),
                          text(f'Gmsh의 STEP 경계 근사 사면체 메시(C3D10)와 CalculiX를 사용했습니다. 지지대당 하중 {fmt(fe["force_per_support_N"]," N")}, 요소 수 {coarse["elements_C3D10"]:,} → {fine["elements_C3D10"]:,}, 롤러 받침부 최대 수직 변위 {fmt(coarse["displacement"]["max_abs_vertical_displacement_mm"]," mm")} → {fmt(fine["displacement"]["max_abs_vertical_displacement_mm"]," mm")}. 메시 변경에 따른 변위 차이는 {fmt(fe["displacement_mesh_change_ratio"]*100,"%")}. 결과 파일은 suite/structural_screen/에 있습니다.'),
                          text('출력 재료 탄성계수는 측정값이 아닌 가정입니다. 지지대 하단 완전 고정·롤러 절점 하중을 적용했고 베이스·볼트·접촉·출력 이방성은 생략했습니다. 변위 수렴은 강도나 응력 수렴을 증명하지 않습니다.',small)])
        story.extend([text('제품 판정',subtitle),
                      text('전체 제작 승인 상태는 UNKNOWN입니다. 굽힘 지그 강도, 체결, 시험기 장착부, 출력 소재와 방향, 슬라이싱, 실제 출력과 단계 하중 시험은 미검증입니다. 필름 정렬 및 폼 압축용 출력 부품은 하중 시험 전 제거해야 합니다. 반경 확인구는 반복 피로시험 장치가 아닙니다.'),
                      text('자료 확인',subtitle),
                      text('저장소: https://github.com/pikachu444/auto-fixture-design',small),
                      text('GitHub Actions 실행: '+run_url,small),
                      text('실행별 suite/index.html에 11건의 상세 보고서가 있습니다.',small)])
        def footer(canvas,document):
            canvas.saveState();canvas.setFont('KoreanReport',8);canvas.setFillColor(colors.HexColor('#607381'))
            canvas.drawString(19*mm,12*mm,'Auto Fixture Design - GitHub Actions 결과')
            canvas.drawRightString(A4[0]-19*mm,12*mm,str(document.page));canvas.restoreState()
        doc.build(story,onFirstPage=footer,onLaterPages=footer)
    from pypdf import PdfReader
    reader=PdfReader(str(output));extracted='\n'.join(page.extract_text() or '' for page in reader.pages)
    assert len(reader.pages)>=2 and '거부 사례와 그 이유' in extracted and all(x['id'] in extracted for x in cases['results'])
    print(f'PDF generated: {output} ({len(reader.pages)} pages)')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--suite',type=Path,default=Path('artifacts/suite'));parser.add_argument('--output',type=Path,default=Path('artifacts/suite/REPORT.pdf'));args=parser.parse_args()
    run(args.suite,args.output)
