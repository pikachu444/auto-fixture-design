# Auto Fixture Design

[![Generate and verify fixtures](https://github.com/pikachu444/auto-fixture-design/actions/workflows/fixture-ci.yml/badge.svg)](https://github.com/pikachu444/auto-fixture-design/actions/workflows/fixture-ci.yml)

시편 치수·물성, 시험기 구성, 프린터 출력 범위를 입력하면 **계산 → 제약 검사 → 실제 CAD 생성 → 파일 재검증 → 보고서**를 실행합니다. CadQuery/OpenCascade의 솔리드 모델을 STEP/STL/3MF로 출력합니다.

## 실행 결과 받기

1. [Actions](https://github.com/pikachu444/auto-fixture-design/actions/workflows/fixture-ci.yml)에서 최신 완료 실행을 엽니다.
2. **Artifacts → fixture-results-커밋SHA**를 다운로드합니다.
3. 압축을 풀고 **`suite/DESIGN_VERIFICATION.pdf`**를 열면 요구조건·계산·CAD 증거·차단 사례·수계산/해석·미검증 범위를 정리한 설계 검증 보고서를 볼 수 있습니다. `suite/REPORT.pdf`는 간단한 실행 요약입니다. `suite/index.html`에는 사례별 상세 보고서가 있고, 각 사례 폴더에는 CAD, HTML/Markdown 보고서, JSON, BOM이 있습니다.

`main`에 코드를 올리거나 PR을 만들 때 자동 실행하며 **Run workflow**로 수동 실행할 수도 있습니다. 저장 기간은 30일입니다. CI 성공은 계산·소프트웨어 회귀 검사 성공이며, 실물 제작 승인이 아닙니다.

## CAD 형상에서 치수를 선택해 파라미터 정의

화면의 **형상 치수 정의** 탭은 편집 가능한 FreeCAD `.FCStd` 문서를 엽니다. 처음에는 사용자 파라미터가 없습니다. CAD 피처 트리의 길이·반경 또는 Sketcher의 구동 치수 중 하나를 선택하고 **이름과 허용 범위를 직접 지정**하면 그 정의가 `.FCStd` 원본에 저장됩니다. 이어서 정의한 값만 변경하고 원본을 재계산해 STEP/STL/3MF와 판정 보고서를 받습니다. 작성된 `.FCStd`를 다시 열어도 정의가 남습니다.

샘플 롤러 지지대에서는 `SupportBlock.Length`를 사용자가 `my_support_width`로 정의하여 폭 32→38 mm를 재생성합니다. 이어 `RollerCradle.Radius`와 `BoltBore1.Radius`를 선택할 수 있으며, 구멍 반경으로 외곽 여유가 2 mm 미만이 되면 CAD 출력을 차단합니다. 이 이름은 샘플 실행에서 사용자가 붙인 예시일 뿐, 화면에 고정된 입력 목록이 아닙니다. CI는 정의·재생성·원본 다시 열기·차단을 실제 FreeCAD로 실행합니다.

신뢰하는 `.FCStd` 문서를 직접 가져와 피처/스케치 치수를 정의할 수도 있습니다. 최종 출력할 솔리드가 표시되지 않으면 형상 트리에서 지정해야 합니다. FreeCAD GUI에서는 스케치를 열고 형상을 선택하여 치수 구속을 추가할 수 있습니다. 저장한 문서를 이 프로그램에 가져오면 그 구동 치수가 후보가 됩니다. **피처 이력이 없는 STEP 형상의 임의 면을 클릭하여 설계 변수를 자동 복원하는 기능은 아닙니다.** 화면의 3D 이미지는 정적이며 CAD 편집은 피처/치수 선택과 값 변경, FreeCAD GUI에서 수행합니다. 출력 강도·장비 장착은 별도 검증입니다.

로컬 실행에는 FreeCADCmd 1.1 계열을 설치하고 실행 파일 경로를 `FREECAD_CMD` 환경변수에 지정해야 합니다. Linux용 CI는 FreeCAD 1.1.4 AppImage를 SHA-256 확인 후 실행합니다. 이전 **소스 변수 변경** 탭은 CadQuery 파일에 미리 선언된 변수를 변경하는 기존 경로로 남겨 두었습니다.

## 구현한 사례

| 유형 | 실제 생성하는 부품 | 계산·검출 항목 |
|---|---|---|
| 3점 굽힘 | 슬롯 베이스·지지대, 금속 롤러 포함 조립체 | 4→8 mm 시편 변경, 간격 64→128 mm, 베이스 선택, 예상 하중·변위, 로드셀·공구·프린터 초과 |
| 필름 인장 | 시편 폭에 맞춘 벤치 정렬 트레이 | 물림 길이, 그립 폭, 예상 하중, 연신에 필요한 이동량 |
| 폼 압축 | 양 대각선의 탈착식 L자 위치 결정구 | 목표 압축률의 입력 응력 기반 하중, 압축판 범위, 가용 이동량 |
| 정적 굽힘 반경 | 반원형 반경 확인구 | 표면 변형률·최소 반경, 출력 크기 |

11개 시나리오: CAD 생성 후보 5개, 의도한 제약 위반 6개. 입력은 가상의 엔지니어링 사례이며 제조사 실험 데이터로 주장하지 않습니다. 설계 근거와 실제 사용 조건은 [ENGINEERING.md](docs/ENGINEERING.md)를 참고하세요.

### CAD 소스가 소유하는 파라미터

기존 11개 실험 규칙과 별도로 **CAD 모델 파라미터** 화면이 있습니다. `models/roller_support.py`, `models/film_tray.py`의 숫자 선언이 형상 치수의 원본이며 `FIXTURE_META`가 항목명·단위·허용 범위를 정의합니다. 프로그램은 CadQuery CQGI로 모델별 선언을 자동 발견해 입력 폼을 만들고, 바꾼 값으로 같은 CAD 소스를 다시 실행합니다. 모델 파일에 적힌 구멍 여유 등의 관계식이 실패하면 CAD를 내보내지 않습니다. 새로운 신뢰 가능한 CadQuery 모델을 `models/`에 추가하면 일반 실행 경로를 재사용하며 서버/화면에 그 형상을 하드코딩할 필요가 없습니다.

예를 들어 롤러 지지대의 `support_width_mm`를 32→38 mm로 바꾸면 재생성한 STEP의 폭도 38 mm가 됩니다. 독립 모델인 필름 트레이의 `specimen_width_mm`를 15→20 mm로 바꾸면 외곽 폭은 27.5→32.5 mm입니다. CI는 두 변형과 모델 내 관계식에 의한 거부를 `artifacts/models/`에 기록합니다.

**입력은 신뢰할 수 있는 로컬 Python CAD 파일로 제한합니다.** 임의 파일 업로드와 기존 STEP 파일의 파라미터 자동 복원은 제공하지 않습니다. STEP/STL/3MF는 내보내기 형상이며, 재편집 가능한 원본은 `.py` CAD 소스입니다. 이 두 신규 모델의 구조해석과 실제 장비 적합성은 아직 검증하지 않았습니다.

새 형상을 등록하려면 `models/새이름.py`에 `FIXTURE_META`와 파일 최상위의 숫자 할당을 같은 이름으로 작성하고, 그 숫자를 형상 작성 코드에 사용한 뒤 최종 출력 부품 하나를 `show_object(...)`로 지정합니다. 예를 들어 `body_width_mm = 12.0`과 메타데이터의 `body_width_mm` 항목을 선언하고 `cq.Workplane("XY").box(body_width_mm, 9, 7)`을 출력하면 화면에서 폭을 바꿀 수 있습니다. 파일을 저장하고 화면을 새로고침하면 모델 목록에 나타납니다. 이 경로는 신뢰할 수 있는 Python 코드만 실행하며 현재 단일 출력 솔리드와 mm 단위의 숫자 입력을 지원합니다. 새 모델의 물리적 검사 기준은 해당 CAD 소스의 관계식과 별도 엔지니어링 검토로 정의해야 합니다.

**현재 제작 승인 상태는 모두 UNKNOWN입니다.** 인장·압축 출력 보조구는 하중 시험 전에 제거합니다. 굽힘 지그의 출력물 강도·체결부·장비 어댑터는 검증 전입니다. 반경 확인구는 반복 폴딩 시험기가 아니며 피로수명을 예측하지 않습니다. 장비를 제어하지 않습니다.

### 구조해석 예비 검토

CI는 생성한 굽힘 지그의 **출력 지지대 STEP**을 Gmsh로 형상 경계에 맞춘 10절점 사면체 메시로 만들고 CalculiX에서 정적 선형 탄성 해석을 실행합니다. 작은 볼트 구멍 주변의 뒤집힌 곡면 요소를 피하려고 2차 절점은 직선 보간합니다. 따라서 곡면은 삼각형 면으로 근사되며 메시 세분화 검사가 필요합니다. 최대 요소 크기를 4→3→2 mm로 줄여 접촉부 수직 변위의 메시 민감도를 기록하며, 실제 FRD 응력장을 읽어 최대 평균 절점 von Mises 응력도 **진단값**으로 기록합니다. 원본 STEP·메시·해석 입력·FRD 결과와 `suite/structural_screen/result.json`을 보관합니다. 별도의 상용 라이선스는 필요 없습니다.

로컬에서도 Gmsh와 CalculiX `ccx`를 설치한 다음 실행할 수 있습니다.

```bash
python -m scripts.run_structural_screen --input examples/bend_8mm.json --material examples/printed_material_ASSUMED.json --output artifacts/structural-001
```

**이 결과로 지그 강도 합격 여부를 판정하지 않습니다.** 예제의 출력 방향별 탄성계수·전단계수는 측정값이 아닌 가정입니다. 입력 모델은 등방성 또는 직교이방성을 지원하며 CAD X/Y/Z와 출력 적층 방향의 대응을 명시해야 합니다. 지지대 바닥을 완전 고정하고 두 지지대가 설계 하중을 절반씩 받는다고 놓았습니다. 실제 베이스·체결부·비선형 롤러 접촉 및 출력 방향별 강도는 모델링하지 않았습니다. 지지대만 해석했으므로 전체 조립체 FEA나 출력물 실험을 대신하지 않습니다.

모든 사례 보고서에는 해당 시편의 하중·이동량·변형률에 대한 **병행 산술 대조**를 담습니다. 굽힘 해석 결과에는 지지대 총단면의 평균 압축응력 및 균일 축압축 변위도 FEA 접촉점 변위와 나란히 보여줍니다. 시편 수계산은 동일 이상화 식의 별도 구현 검사이며 실제 실험 검증은 아닙니다. 지지대 규모 비교는 구멍과 국부 접촉을 생략하므로 FEA와 일치해야 한다는 판정 기준으로 쓰지 않습니다.

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

화면에는 **기존 실험 예제**와 **CAD 모델 파라미터**가 따로 있습니다. 후자는 CAD 소스에서 항목을 읽어 폼을 만들고 STEP/STL/3MF를 재생성합니다. 형상은 정적 미리보기이며 회전 가능한 3D 편집기와 유한요소해석 실행 버튼은 없습니다. 기존 굽힘 조립체의 예비해석은 위 CLI 명령 또는 GitHub Actions에서 별도로 실행합니다. 자동으로 지그를 최적화하거나 대체 설계를 찾지는 않습니다.

## 명령줄 / 자동화

가상환경을 활성화한 터미널에서:

```bash
python -m fixturelab suite --output artifacts/run-001
python -m fixturelab generate --input examples/bend_8mm.json --output artifacts/custom-001
python -m fixturelab model --model roller_support --parameters examples/roller_width_38.json --output artifacts/model-001
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

설계 검증 PDF는 구조해석 결과까지 필요합니다. Gmsh와 CalculiX를 설치한 환경에서 suite 실행 후 다음을 추가로 실행합니다.

```bash
python -m scripts.run_structural_screen --input examples/bend_8mm.json --material examples/printed_material_ASSUMED.json --output artifacts/test-suite/structural_screen
python scripts/build_ci_report.py --suite artifacts/test-suite --output artifacts/test-suite/REPORT.pdf
python -m scripts.build_design_verification_report --suite artifacts/test-suite --output artifacts/test-suite/DESIGN_VERIFICATION.pdf
```

브라우저 검사는 Chromium에서 시편 폭을 변경하고 실제 CAD를 생성한 뒤 ZIP 내부 치수가 바뀌었는지 확인합니다. 이어서 이동량 부족 사례가 거부되는지 검사합니다. GitHub Actions는 브라우저 실행에 필요한 Linux 시스템 라이브러리도 설치합니다.
CAD 소스 파라미터 화면에서도 롤러 지지대 폭 변경과 관계식 위반 차단을 브라우저에서 검사합니다.

로컬 PDF 생성에는 한국어 TrueType 글꼴이 필요합니다. CI에서는 `fonts-nanum`을 설치해 PDF에 글꼴을 포함합니다. Windows에서는 시스템의 맑은 고딕을 사용합니다.

## 구성

- `fixturelab/`: 계산·파라메트릭 CAD·검증·보고서·로컬 웹 프로그램
- `models/`: 모델 내부에 숫자 파라미터·범위·형상 관계식을 가진 CadQuery 원본
- `examples/`: 편집 가능한 입력 JSON 및 기대 판정 목록
- `tests/`: 독립 보 공식, 경계, 오류 입력, 파일 재읽기 검사
- `.github/workflows/fixture-ci.yml`: 실제 실행·보고서·아티팩트 자동화
- `docs/ENGINEERING.md`: 식, 가정, 근거와 미구현 범위
- `docs/planning/`: 기존 상세 기획과 미실행 제품 인수 검사
- `legacy/`: 앞서 실행했던 첫 굽힘 데모와 당시 결과 보존

의존성 직접 버전을 고정하고 실제 설치된 전체 버전은 CI의 `resolved-environment.txt`에 기록합니다. 결과에는 입력 SHA-256, 실행 시간, 코드 커밋과 라이브러리 버전이 포함됩니다. G-code, 실제 출력, **지지대 외의 전체 조립체 FEA**, 피로시험 및 기존 CAD 파라미터 가져오기는 아직 구현하지 않았습니다.
