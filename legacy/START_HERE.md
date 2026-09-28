# 파라메트릭 실험 지그 — 실제 실행 데모

이 폴더 하나를 Codex 프로젝트로 전달하면 됩니다. 상세 기획, 실제 실행 코드, CAD, 검증 결과를 포함합니다.

## 결과부터 보기

- `outputs/cad_comparison.png`: 실제 CAD를 렌더링한 수정 전후 비교.
- `outputs/cad_viewer.html`: 별도 서버나 인터넷 없이 브라우저에서 열 수 있는 회전 뷰어. 단순 Canvas 메시 뷰어이며 CAD 편집기는 아닙니다.
- `outputs/modified/assembly.step`: 수정한 조립체, 단위 mm.
- `outputs/modified/printed_*.stl`, `printed_*.3mf`: 베이스와 좌우 지지대 각각의 출력용 형상. 각각 바닥 Z=0으로 이동했습니다.
- `outputs/results.json`: CAD 생성·재읽기·메시·간섭·출력 범위 검사 결과.
- `EXECUTION_REPORT.md`: 검증 범위와 미완료 항목.

## 실행

Python 3.12 환경에서 프로젝트 최상위 폴더를 작업 폴더로 사용합니다.

```bash
python -m venv .venv
```

Windows PowerShell:
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_demo.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

macOS / Linux:
```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_demo.py
.venv/bin/python -m unittest discover -s tests -v
```

의존성 설치에는 인터넷이 필요합니다. 생성과 검사는 로컬 실행입니다. `run_demo.py`를 다시 실행하면 `outputs/`의 같은 이름 파일을 덮어씁니다. 결과를 보존하려면 먼저 복사하세요. 테스트한 OS는 Linux, Python 3.12.14입니다. 다른 OS에서의 설치는 아직 검증하지 않았습니다.

## 수정할 곳

- `inputs/bending.json`: 초기·변경 시편 물성/치수, 참조 장비, 프린터 출력 범위.
- `src/fixture.py`: 요구 간격·하중 계산, 베이스 선택, 파라메트릭 형상.
- `run_demo.py`: 생성, 검증, STEP/STL/3MF 내보내기, 이미지·뷰어 생성.
- `tests/test_rules.py`: 독립 보 공식 및 경계/거부 조건 회귀 테스트.
- `planning/fixture_plan.md`: 전체 제품 상세 기획 v1.1. 인장·압축·굽힘·반복 굽힘 확장 포함.
- `CODEX_TASK.md`: 후속 개발 작업 지시서.

## 범위

현재는 직사각형 시편의 저변형 3점 굽힘 데모입니다. 지지 간격 40–160 mm, 시편 폭 최대 16 mm, 목표 변형률 최대 1%를 적용합니다. 지지대·베이스 단면과 롤러는 고정 템플릿이며 임의 형상 입력을 자동 해석하지 않습니다. 베이스 160/220 mm 두 후보 중 조건을 만족하는 작은 후보를 선택합니다. 일반 최적화기는 아닙니다.

이 예제는 새로 작성한 CadQuery 템플릿입니다. 사용자의 기존 CAD 파일을 가져와 수정하는 기능은 아직 없습니다. 사진에서 CAD를 복원하거나 원본 설계를 복제한 것이 아닙니다.

3MF는 형상만 포함합니다. 슬라이싱, 출력 시간/재료량 산정, G-code 생성, 실제 출력은 미실행입니다. 금속 롤러·가압봉·볼트는 출력 대상으로 분류하지 않습니다. 하중 전달부 장착, 체결 완성, 롤러 이탈 방지 및 출력물 강도 검증 전에는 실험에 투입할 수 없습니다.
