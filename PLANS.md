# 2026-06-17 계정-ID 매핑 입력 포커스 유지

## Purpose
- `계정-ID 매핑` 편집 중 일반 키보드 타이핑이 끊기고 붙여넣기로만 입력되는 문제를 해결한다.

## Implementation Summary
- 계정 매핑 테이블 행의 React `key`가 입력값을 포함해 타이핑마다 행을 재마운트하던 문제를 고쳤다.
- 행 `key`를 편집 중 바뀌지 않는 값으로 바꿔 입력 포커스가 유지되게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 공시원문 목차 분리 전문가 워크스페이스

## Purpose
- 5회 개선 루프를 통해 `공시원문 목차 분리`를 단일 파일 중심 화면에서 공시 데이터 처리 전문가가 폴더 전체 coverage를 판단하고 산출물을 만들 수 있는 작업대로 바꾼다.

## Implementation Summary
- 폴더 단위 목차 스캔 API를 추가해 목차 ID, 제목, 파일 수, coverage, 샘플 파일을 반환하게 했다.
- `공시원문 목차 분리` 화면을 `작업 기준`, `목차 Coverage`, `렌더링 검토` 중심으로 재배치했다.
- 스캔 결과 행을 선택하면 저장 대상 목차와 샘플 파일이 함께 바뀌고, 같은 화면에서 목차 렌더링과 목차 저장을 실행하게 했다.
- 2026 사채발행 HTML 폴더가 기본 설정이 없을 때의 샘플 경로가 되게 했다.
- `목차 스캔`, `목차 저장`, `목차 렌더링` 용어를 glossary에 추가하고 UI/tests와 맞췄다.

## Verification
- Passed: `python3 -m py_compile src/finiq/market_desk/web/disclosure_html_sections.py src/finiq/market_desk/web/routers/workflows.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` (148 tests).
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py -q` (23 tests).
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Checked: `resources/KIND/bond_issuance/kind_html_contents_grouped/2026`에서 369개 HTML 모두 `toc_1`, `toc_2`가 100% coverage로 스캔됨.
- Checked: 브라우저에서 `http://localhost:3000/html-section-split` 화면 DOM에 작업 기준, 목차 Coverage, 렌더링 검토 영역이 표시됨. 현재 실행 중인 `8765` 백엔드는 변경 전 프로세스라 새 API 브라우저 호출은 재시작 후 확인 필요.

# 2026-06-17 Parquet 미리보기 문구 및 실패분 이어서 실행

## Purpose
- `Quantiwise - Parquet 미리보기`에서 선택 전 빈 상태가 Excel Sheet 기준 문구로 보이는 문제를 고친다.
- `Parquet 변환하기`에서 기존 성공분은 건너뛰고 누락된 실패분만 다시 변환할 수 있게 한다.

## Implementation Summary
- Parquet 미리보기 빈 상태 문구를 `Parquet 파일을 선택하세요.`로 바꿨다.
- 변환 payload에 `resume_failed_only`를 추가하고, `실패분 이어서 실행` 버튼에서 이 옵션을 전달하게 했다.
- 백엔드 변환은 기존 `manifest.json`과 데이터 경로의 Sheet Parquet를 기준으로 완료된 원천 파일/Sheet를 `resume_skipped`로 기록하고, 누락된 Sheet만 임시 저장 후 최종 Parquet로 승격한다.
- 이어서 실행 결과 manifest/result에 `resume_failed_only`, `resume_skipped`를 포함하고, 기존 manifest 출력과 새 출력을 합쳐 결과 탐색이 유지되게 했다.
- 로컬 저장 설정이 API 기본 매핑 테스트에 섞이지 않도록 해당 테스트의 계정 매핑 설정을 격리했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/routers/assets_excel.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/test_assets_excel.py -q` (32 tests).
- Passed: `python3 -m pytest tests/market_desk/test_server.py tests/market_desk/test_kind_web_app.py::test_api_settings_persists_asset_excel_account_mappings -q`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 Quantiwise 보조 설명 문구 제거

## Purpose
- `Parquet 변환하기`와 `Quantiwise - 병합하기` 화면에서 의미 없는 보조 설명 문구를 제거한다.

## Implementation Summary
- Quantiwise 화면 헤더의 반복적인 `기능` 설명 문구를 제거했다.
- 변환/병합 화면 오른쪽 설정 패널은 유지하고, 빈 채우기용 설명 문구만 제거했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 계정-ID 매핑 완료 저장

## Purpose
- `계정-ID 매핑`을 수정한 뒤 `완료`를 눌러도 수정값이 저장되지 않는 문제를 해결한다.

## Implementation Summary
- `asset_excel_account_mappings`를 앱 설정에 저장/로드할 수 있게 추가했다.
- 계정 매핑 조회 API가 저장된 매핑이 있으면 기본 매핑 대신 저장된 매핑을 반환하게 했다.
- `완료` 버튼이 편집 모드만 끄지 않고, 검증 통과 후 매핑을 `/api/settings`에 저장하게 했다.
- 계정 매핑 설정 저장 회귀 테스트를 추가했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/config.py src/finiq/market_desk/web/routers/config.py src/finiq/market_desk/web/routers/assets_excel.py src/finiq/market_desk/web/app.py src/finiq/data/assets_excel.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py::test_api_settings_persists_asset_excel_account_mappings tests/test_assets_excel.py::test_custom_account_mappings_reject_duplicate_account_names -q`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py tests/test_partial_save.py tests/test_dict_persistence.py tests/test_persistence_api.py -q` (27 tests).
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 공시원문 목차 분리 및 렌더링

## Purpose
- `resources/KIND/bond_issuance/kind_html_contents_grouped/2026` 형태의 KIND 본문 HTML을 목차별로 분리하고, 특정 목차만 저장/렌더링할 수 있게 한다.

## Implementation Summary
- KIND 본문 HTML의 `h2#toc_N` 경계를 기준으로 목차 섹션을 분리하는 백엔드 유틸리티를 추가했다.
- 단일 HTML의 목차 목록 조회, 특정 목차 HTML 렌더링, 폴더 단위 특정 목차 저장 API를 추가했다.
- `공시원문 목차 분리` 화면을 추가해 입력/결과 경로, 목차 선택, 저장 실행, 단일 파일 목차 읽기와 렌더링 미리보기를 지원하게 했다.
- UI 용어 glossary와 HTML workflow 내비게이션을 새 화면에 맞게 갱신했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/market_desk/web/disclosure_html_sections.py src/finiq/market_desk/web/routers/workflows.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` (147 tests).
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py -q` (23 tests).
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Checked: `resources/KIND/bond_issuance/kind_html_contents_grouped/2026/20260422000832.html`에서 `toc_2` 렌더링 결과에 `전환사채권 발행결정`만 포함되고 `주요사항보고서`는 제외됨.

# 2026-06-17 계정-ID 매핑 계정명 중복검사

## Purpose
- `계정-ID 매핑`에서 같은 `account_name`을 여러 Sheet에 지정하는 입력을 실행 전에 막는다.

## Implementation Summary
- 백엔드 계정 매핑 정규화에서 `account_name` 중복을 `account_id`, `sheet_name` 중복과 동일하게 거부하게 했다.
- 변환 화면의 사전 검증에서도 중복 계정명을 감지해 실행을 막게 했다.
- 중복 계정명을 거부하는 regression test를 추가했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py`.
- Passed: `python3 -m pytest tests/test_assets_excel.py -q` (31 tests).
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 Quantiwise 변환 결과 메시지 및 manifest 축약

## Purpose
- `Quantiwise - 변환하기` 화면의 기존 결과 감지 경고 문구를 제거한다.
- 변환 완료 결과에서 건너뛴 Sheet 개수만이 아니라 파일, Sheet, 이유를 확인할 수 있게 한다.
- `manifest.json`에 긴 날짜 목록과 샘플 행을 저장하지 않고 날짜 구간은 시작일/종료일만 기록한다.

## Implementation Summary
- 변환 화면의 기존 결과 감지 경고 블록을 제거했다.
- 변환 완료 상태와 job 로그에 `건너뛴 Sheet 상세`를 추가하고, 완료 후 결과 표도 실제 job 결과의 skipped 목록을 보게 했다.
- 품질 payload에서 `sample_rows` 생성을 제거하고 결과 UI의 `최근 샘플` 영역을 제거했다.
- `date_index` metadata를 제거하고 `date_segments`를 `start`/`end`만 남기도록 축약했다.
- `docs/assets-excel-conversion.md`와 regression tests를 새 metadata 계약에 맞게 갱신했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Not run: 실제 Quantiwise 리소스 변환 실행은 사용자가 금지했으므로 수행하지 않았다.
