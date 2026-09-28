# 시험 지그 프로그램 개발 인계 패키지 1.1

## 읽는 순서
1. fixture_plan.md: 장비 선정, 기존 13개 시험 시나리오와 추가 6개 제작 시나리오, CAD·판정·화면·개발 명세.
2. equipment_profiles.json: 제조사 확인값과 미확인 항목. 실제 설치 장비의 인증 데이터가 아닙니다.
3. scenario_inputs.json: 개발용 입력. 실제 소재의 보증 물성이 아닙니다.
4. acceptance_tests.csv: 제품 구현 후 실행할 53개 수용시험. 현재 제품 테스트는 미실행입니다.
5. verify_planning_examples.py와 planning_calculation_results.json: 이번 기획의 수치 예제 검산과 실행 결과.

## 지금 완료된 것
상세 기획, 공개 장비 사양 조사, 개발 입력 정의, 수용시험 명세, 기획 예제 수치 검산.

## 아직 개발하지 않은 것
사용자 프로그램, CadQuery 기본 지그 템플릿과 선택적 FreeCAD 어댑터, 실제 CAD 자동 수정, 간섭·구조 해석, 실물 검증.

## 개발 시작 지시
fixture_plan.md 18절에 따라 공통 계산 엔진부터 구현하십시오. 제조사 미확인값을 가상값으로 덮어쓰지 말고, 필수 근거가 없는 검증은 UNKNOWN으로 두십시오. 네 시험 모두 대응하되 굽힘의 설계부터 3D 프린팅 제작 파일까지 전체 흐름을 먼저 완성하십시오. 기본 CAD 엔진은 CadQuery이고 FreeCAD는 기존 자산과 확인·편집에 사용합니다. 시편 치수와 목표 시험 조건은 고정하고 지그 변수만 허용 범위에서 수정하십시오. 제품 검증 시 acceptance_tests.csv의 실행 상태를 실제 결과로 갱신하십시오.

## 기획 검산 재실행
Python 표준 라이브러리만 필요합니다. 패키지 폴더에서 실행:
`python verify_planning_examples.py`

결과 파일은 기획 수치의 확인 기록이며 완성 프로그램 테스트 기록이 아닙니다.

## 3D 프린팅 확장
manufacturing_profiles.json, printing_scenarios.json, print_acceptance_tests.csv를 함께 읽으십시오. 추가 26개 수용시험을 포함해 전체 제품 수용시험은 79개입니다. 제품 수용시험은 아직 실행하지 않았습니다.

이번 개정은 자연어 변경 제안, CadQuery 원본, 출력 방향과 레시피, 프린터 프로파일, 3MF·G-code 구분, 출력물과 금속 부품 조립, 후가공·실물 검사를 정의합니다. 특정 프린터용 G-code와 실제 출력물은 아직 없습니다.

추가 기획 수치 검산은 `python verify_printing_examples.py`로 실행하고 printing_calculation_results.json에 저장합니다. 기존 검산 코드도 별도로 유지합니다.
