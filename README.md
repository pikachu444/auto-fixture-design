# Auto Fixture Design

[![Generate and verify fixtures](https://github.com/pikachu444/auto-fixture-design/actions/workflows/fixture-ci.yml/badge.svg)](https://github.com/pikachu444/auto-fixture-design/actions/workflows/fixture-ci.yml)

시편 치수·물성, 시험기 구성, 프린터 출력 범위를 입력하면 **계산 → 제약 검사 → 실제 CAD 생성 → 파일 재검증 → 보고서**를 실행합니다. CadQuery/OpenCascade의 솔리드 모델을 STEP/STL/3MF로 출력합니다.

## 실행 결과 받기

1. [Actions](https://github.com/pikachu444/auto-fixture-design/actions/workflows/fixture-ci.yml)에서 최신 완료 실행을 엽니다.
2. **Artifacts → fixture-results-커밋SHA**를 다운로드합니다.
3. 압축을 풀고 `suite/index.html`을 열면 전체 사례를 볼 수 있습니다. 각 사례 폴더에 CAD, HTML/Markdown 보고서, JSON, BOM이 있습니다.

`main`에 코드를 올리거나 PR을 만들 때 자동 실행하며 **Run workflow**로 수동 실행할 수도 있습니다. 저장 기간은 30일입니다. CI 성공은 계산·소프트웨어 회귀 검사 성공이며, 실물 제작 승인이 아닙니다.

## 구현한 사례

| 유형 | 실제 생성하는 부품 | 계산·검출 항목 |
|---|---|---|
| 3점 굽힘 | 슬롯 베이스·지지대, 금속 롤러 포함 조립체 | 4→8 mm 시편 변경, 간격 64→128 mm, 베이스 선택, 예상 하중·변위, 로드셀·공구·프린터 초과 |
| 필름 인장 | 시편 폭에 맞춘 벤치 정렬 트레이 | 물림 길이, 그립 폭, 예상 하중, 연신에 필요한 이동량 |
| 폼 압축 | 양 대각선의 탈착식 L자 위치 결정구 | 목표 압축률의 입력 응력 기반 하중, 압축판 범위, 가용 이동량 |
| 정적 굽힘 반경 | 반원형 반경 확인구 | 표면 변형률·최소 반경, 출력 크기 |

11개 시나리오: CAD 생성 후보 5개, 의도한 제약 위반 6개. 입력은 가상의 엔지니어링 사례이며 제조사 실험 데이터로 주장하지 않습니다. 설계 근거와 실제 사용 조건은 [ENGINEERING.md](docs/ENGINEERING.md)를 참고하세요.

**현재 제작 승인 상태는 모두 UNKNOWN입니다.** 인장·압축 출력 보조구는 하중 시험 전에 제거합니다. 굽힘 지그의 출력물 강도·체결부·장비 어댑터는 검증 전입니다. 반경 확인구는 반복 폴딩 시험기가 아니며 피로수명을 예측하지 않습니다. 장비를 제어하지 않습니다.

## 로컬 프로그램 실행

Python 3.12 환경이 필요합니다.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m fixturelab serve
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m fixturelab serve
```

브라우저에서 `http://127.0.0.1:8765`를 엽니다. 사례를 선택하고 입력을 수정한 다음 **CAD 생성 및 검증 실행**을 누릅니다. 실제 생성 보고서를 표시하고 ZIP을 다운로드합니다. 로컬 접속만 허용하며 CAD 생성은 시간 제한이 있는 별도 프로세스에서 수행합니다.

## 명령줄 / 자동화

가상환경을 활성화한 터미널에서:

```bash
python -m fixturelab suite --output artifacts/run-001
python -m fixturelab generate --input examples/bend_8mm.json --output artifacts/custom-001
```

결과가 섞이지 않도록 출력 디렉터리는 비어 있어야 합니다. 재실행에는 새 디렉터리 이름을 사용하세요. 단일 사례의 종료 코드: 0=계산 완료·검토 필요, 2=설계 제약 위반, 그 외=계산/입력 오류. suite는 기대 판정과 일치해야 0으로 끝납니다. 거부 사례를 무조건 오류로 취급하지 않습니다.

## 테스트

```bash
python -m pip install -r requirements-dev.txt
python -m pytest --junitxml=artifacts/unit-tests.xml
python -m fixturelab suite --output artifacts/test-suite
python -m playwright install chromium
python scripts/browser_smoke.py
```

브라우저 검사는 Chromium에서 시편 폭을 변경하고 실제 CAD를 생성한 뒤 ZIP 내부 치수가 바뀌었는지 확인합니다. 이어서 이동량 부족 사례가 거부되는지 검사합니다. GitHub Actions는 브라우저 실행에 필요한 Linux 시스템 라이브러리도 설치합니다.

## 구성

- `fixturelab/`: 계산·파라메트릭 CAD·검증·보고서·로컬 웹 프로그램
- `examples/`: 편집 가능한 입력 JSON 및 기대 판정 목록
- `tests/`: 독립 보 공식, 경계, 오류 입력, 파일 재읽기 검사
- `.github/workflows/fixture-ci.yml`: 실제 실행·보고서·아티팩트 자동화
- `docs/ENGINEERING.md`: 식, 가정, 근거와 미구현 범위
- `docs/planning/`: 기존 상세 기획과 미실행 제품 인수 검사
- `legacy/`: 앞서 실행했던 첫 굽힘 데모와 당시 결과 보존

의존성 직접 버전을 고정하고 실제 설치된 전체 버전은 CI의 `resolved-environment.txt`에 기록합니다. 결과에는 입력 SHA-256, 실행 시간, 코드 커밋과 라이브러리 버전이 포함됩니다. G-code, 실제 출력, FEA, 피로시험 및 기존 CAD 파라미터 가져오기는 아직 구현하지 않았습니다.
