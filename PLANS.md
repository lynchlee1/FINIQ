# 2026-06-17 결과 탐색 파일명 및 컬럼 폭 정리

## Purpose
- `결과 탐색`의 `파일` 컬럼이 Parquet 경로나 저장 경로가 아니라 원본 Excel 제목을 보여주게 한다.
- 결과 테이블 컬럼 폭이 내용 길이에 따라 흔들리지 않게 한다.

## Implementation Summary
- `파일` 컬럼 표시값과 정렬값을 output path 대신 `file_name`/`relative_path`/`sources`에서 가져온 원본 Excel 제목으로 바꿨다.
- `결과 탐색` 테이블에 `table-fixed`와 컬럼별 비율 폭을 적용했다.
- 긴 Sheet, ID, 계정, 파일, 구간 값은 컬럼 폭 안에서 말줄임 처리하고 전체 값은 title로 확인할 수 있게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 기존 데이터 경로 결과 탐색 표시

## Purpose
- `결과 탐색`에서 새 변환 job을 실행하지 않아도 선택한 `데이터 경로`의 기존 변환 결과를 볼 수 있게 한다.

## Implementation Summary
- 데이터 경로 검사 API가 반환하는 manifest `outputs`를 `결과 탐색` 표시 소스에 추가했다.
- 데이터 경로 변경 시 이전 경로의 검사 결과를 즉시 비워 다른 경로 결과가 잠깐 남지 않게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 결과 탐색 컬럼 정렬

## Purpose
- `결과 탐색` 테이블에서 컬럼 헤더를 눌러 결과를 정렬할 수 있게 한다.
- 특히 `구간` 기준 정렬로 같은 날짜 구간의 Sheet Parquet 결과가 인접하게 보이도록 한다.

## Implementation Summary
- `결과 탐색` 표시 배열에만 적용되는 정렬 상태를 추가했다.
- Sheet, ID, 계정, 파일, 행, 코드, 결측률, 구간 헤더를 클릭 가능한 정렬 헤더로 바꿨다.
- 숫자 컬럼은 숫자값으로, `구간`은 화면에 표시되는 `start~end` 구간 문자열로 안정 정렬하게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 공시원문 목차 분리 작업 기준 Row Box 재정리

## Purpose
- `공시원문 목차 분리` 화면의 `작업 기준` 영역이 하나의 큰 카드처럼 보여 `1 Row = 1 Box` 원칙을 어기는 문제를 고친다.
- 입력, 실행, 상태 row가 각각 독립 박스로 인식되게 해 공시 데이터 처리자가 화면 구조를 바로 판단할 수 있게 한다.

## Implementation Summary
- `html-section-split` 화면에서 `HtmlWorkflowCard`/`HtmlWorkflowForm` 래핑을 제거했다.
- `입력 경로`, `결과 경로`, `저장 대상 목차`, `최대 처리 건수`, `렌더링 문서`, 각 실행 액션, `작업 상태`를 `작업 기준` 섹션의 독립 row box로 배치했다.
- 액션 버튼 묶음 컨테이너도 제거해 `2026 샘플`, `첫 문서 목차`, `목차 스캔`, `목차 렌더링`, `목차 저장`이 모두 직계 row box가 되게 했다.
- `스캔 결과`, `작업 상태` 용어를 glossary에 추가했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `python3 -m py_compile src/finiq/market_desk/web/disclosure_html_sections.py src/finiq/market_desk/web/routers/workflows.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` (149 tests).
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py -q` (23 tests).
- Checked: `resources/KIND/bond_issuance/kind_html_contents_grouped/2026` preview/inspect returns 369 documents, 2 section types, 0 failures.
- Checked: 브라우저 DOM에서 `작업 기준` 제목 줄을 제외한 11개 직계 children이 모두 border/rounded row box로 렌더링됨.
- Checked: 브라우저 스크린샷 `/tmp/finiq-html-section-split-row-box.png`에서 상단 큰 작업 카드가 제거됨.

# 2026-06-17 페이지 이동 후 실행 로그 복구

## Purpose
- 실행 중인 백엔드 job이 있는데도 다른 페이지로 이동했다가 돌아오면 실행 로그가 사라지는 문제를 해결한다.

## Implementation Summary
- `useJobPolling`이 시작한 job id를 페이지 경로와 polling endpoint 기준으로 `sessionStorage`에 저장하게 했다.
- 페이지 재진입 시 저장된 job id로 polling을 재개해 백엔드의 `progress_log`를 다시 표시하게 했다.
- 페이지 언마운트 시 pending timeout을 정리하고, 완료/실패/중단 또는 stale job 404에서는 저장된 job id를 제거하게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 계정-ID 매핑 입력 포커스 유지

## Purpose
- `계정-ID 매핑` 편집 중 일반 키보드 타이핑이 끊기고 붙여넣기로만 입력되는 문제를 해결한다.

## Implementation Summary
- 계정 매핑 테이블 행의 React `key`가 입력값을 포함해 타이핑마다 행을 재마운트하던 문제를 고쳤다.
- 행 `key`를 편집 중 바뀌지 않는 값으로 바꿔 입력 포커스가 유지되게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 공시원문 목차 분리 엄격 1 Row Box 보완

## Purpose
- `공시원문 목차 분리` 화면에서 카드 안 카드처럼 보이는 구조를 줄이고, 스캔 전에도 실제 목차를 볼 수 있게 한다.
- 사용자가 전체 스캔 전에 첫 HTML 문서의 목차를 확인하고 바로 렌더링 대상을 잡을 수 있게 한다.

## Implementation Summary
- 첫 HTML 파일의 목차를 반환하는 `preview_disclosure_html_sections_payload`와 `/api/disclosures/html/sections/preview` API를 추가했다.
- 데이터 영역의 `HtmlWorkflowCard` 래핑을 제거하고, `전체 목차 목록`, `문서 목록`, `렌더링 검토`를 unframed section + row box stack으로 바꿨다.
- 스캔 전 `첫 문서 목차` 버튼을 추가하고, 결과를 전체 목차/문서/렌더링 검토 영역에 바로 반영하게 했다.
- 작업 기준의 요약 수치를 별도 카드가 아닌 한 줄 상태 정보로 바꿨다.
- `첫 문서 목차` 용어를 glossary에 추가하고 UI/tests와 맞췄다.

## Verification
- Passed: `python3 -m py_compile src/finiq/market_desk/web/disclosure_html_sections.py src/finiq/market_desk/web/routers/workflows.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` (149 tests).
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py -q` (23 tests).
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Checked: `resources/KIND/bond_issuance/kind_html_contents_grouped/2026` 첫 문서 목차가 `toc_1`, `toc_2`로 반환됨.
- Checked: 브라우저 DOM에서 `첫 문서 목차`, `전체 목차 목록`, `문서 목록`, `렌더링 검토`가 표시됨.

# 2026-06-17 공시원문 목차 분리 1 Row 1 Box 재설계

## Purpose
- `1 Row = 1 Box` 원칙으로 `공시원문 목차 분리` 화면을 다시 설계한다.
- 공시 데이터 처리 전문가가 폴더 전체 목차 목록, 문서별 목차, 목차 변형, 렌더링 대상 문서를 한 화면에서 판단할 수 있게 한다.

## Implementation Summary
- 목차 스캔 응답에 문서별 목차 목록(`documents`)과 목차 제목 변형(`title_variants`)을 추가했다.
- `전체 목차 목록`, `문서 목록`, `렌더링 검토` 세 패널로 화면을 재구성했다.
- 전체 목차, 문서, 선택 문서의 목차를 모두 독립 row box로 표시하게 했다.
- `2026 샘플` 바로가기, `저장 대상 목차`, `렌더링 문서` 입력을 추가해 스캔-선택-미리보기-저장 흐름을 줄였다.
- 같은 `toc_2` 안에 섞인 전환사채권/교환사채권/신주인수권부사채권 제목 변형을 box 내부에서 바로 확인하게 했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/market_desk/web/disclosure_html_sections.py src/finiq/market_desk/web/routers/workflows.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` (148 tests).
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py -q` (23 tests).
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Checked: `resources/KIND/bond_issuance/kind_html_contents_grouped/2026`에서 369개 문서, `toc_1`/`toc_2` 100% coverage, `toc_2` 제목 변형 3종이 스캔됨.
- Checked: 브라우저 DOM에서 `2026 샘플`, `전체 목차 목록`, `문서 목록`, `렌더링 검토`, `저장 대상 목차`, `렌더링 문서`가 표시됨.

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
