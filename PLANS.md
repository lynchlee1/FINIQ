# 2026-06-18 Quantiwise legacy account mapping 제외

## Purpose
- 출력 폴더에 이전 버전이 남긴 `account_mapping.parquet`가 있어도 `Parquet 모아보기`, 미리보기, 병합 후보 스캔이 계정 데이터로 오인하지 않게 한다.
- footer metadata가 없는 실제 계정 Parquet는 계속 에러로 처리한다.

## Implementation Summary
- `account_mapping.parquet`를 생성/읽기 계약으로 복구하지 않고, `code_name_mapping.parquet`와 함께 비계정 Parquet 제외 목록에만 추가했다.
- 출력 스캔, 미리보기 파일 검증, 병합 후보 탐색, 선택 파일 검증, 실패분 이어서 실행의 기존 출력 감지에서 같은 제외 목록을 사용하게 했다.
- stale `account_mapping.parquet`가 있어도 출력 스캔이 성공하고 실제 계정 Parquet만 반환하는 regression test를 추가했다.
- `docs/assets-excel-conversion.md`에 legacy `account_mapping.parquet` 제외 동작을 기록했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py -q`.
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/routers/assets_excel.py`.

# 2026-06-18 Quantiwise manifest/account mapping 제거

## Purpose
- Quantiwise 기능이 `manifest.json`과 `account_mapping.parquet`에 의존하지 않게 한다.
- 계정-ID 매핑 원본은 앱 설정에 두고, 생성된 계정 Parquet는 footer metadata만으로 식별하게 한다.
- `Parquet 모아보기`, `Quantiwise - Parquet 미리보기`, `Quantiwise - 병합하기`에서 footer metadata가 없으면 fallback 계산 없이 에러로 처리한다.

## Implementation Summary
- 계정 Parquet 저장 시 footer metadata에 `account_id`, `account_name`, `date_start`, `date_end`, `rows`, `columns`, `non_null_cells`, `total_cells`, `missing_ratio`만 기록하게 했다.
- `manifest.json`과 `account_mapping.parquet` 생성/읽기 경로를 제거했고, `실패분 이어서 실행`은 예상 output filename이 이미 있으면 건너뛰게 했다.
- Code-Name mapping Parquet는 `code`, `name`만 저장하게 했다.
- 출력/미리보기/병합 UI에서 원본 Sheet/source 기반 표시를 제거하고, Sheet 정렬 key와 Parquet preview의 Sheet 선택 UI를 없앴다.
- 변환/미리보기/병합 테스트를 footer metadata 계약 기준으로 갱신하고, footer metadata 누락 시 에러가 나는 regression test를 추가했다.
- `docs/assets-excel-conversion.md`를 manifest 없는 저장 계약으로 갱신했다.

## Verification
- `python3 -m pytest tests/test_assets_excel.py -q`
- `python3 -m pytest tests/market_desk/test_server.py -q`
- `python3 -m pytest tests/market_desk/test_kind_web_app.py -q`
- `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`

# 2026-06-18 Quantiwise Parquet 모아보기 누락 수정

## Purpose
- `Quantiwise - Parquet 미리보기`의 `Parquet 모아보기`에서 manifest에 없는 실제 Parquet 파일이 누락되지 않게 한다.
- `Quantiwise - 병합하기`에서 duplicate suffix가 붙은 같은 계정 Parquet 파일도 같은 병합 후보로 묶이게 한다.
- 두 화면에서 `ID`, `행`, `코드`, `결측률`, `값 있음`, `전체 셀`, `구간`이 누락되지 않게 한다.

## Implementation Summary
- `Parquet 모아보기` row 생성도 manifest `outputs`와 실제 폴더 `parquet_files`를 합쳐 표시하게 했다.
- 프론트엔드와 백엔드의 계정명 추출 규칙을 `<account>_<YYYYMMDD>_<YYYYMMDD>`, `_2`, `__2` suffix 모두 처리하도록 맞췄다.
- 병합 결과처럼 manifest metadata가 `accounts`에만 있는 경우도 `outputs` row로 노출하게 했다.
- manifest에 없는 실제 Parquet 파일은 inspect 단계에서 Parquet를 읽어 `ID`, row/code count, missing ratio, non-null/total cell count, date segment를 계산하게 했다.
- `close_20200103_20200104__2.parquet` 같은 duplicate output을 병합 선택과 Parquet preview fallback에서 같은 계정으로 인식하는 regression test를 추가했다.
- `Parquet 모아보기`와 `병합대상 모아보기` formatter 기준으로 직접 API 결과를 검증해 두 표 모두 누락 셀이 없음을 확인했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py -k "duplicate_suffix or groups_duplicate_suffix" -vv`.
- Passed: `python3 -m pytest tests/test_assets_excel.py -vv`.
- Passed: `python3 -m pytest tests/market_desk/test_server.py -vv`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-18 Quantiwise 병합 대상 필터 및 명칭

## Purpose
- `Quantiwise - 병합하기`의 후보 목록에서 같은 계정 파일이 1개뿐인 Parquet는 숨긴다.
- 병합 화면의 `Parquet 모아보기` 제목을 `병합대상 모아보기`로 바꾼다.

## Implementation Summary
- 병합 화면 전용 row 생성 함수에서 파일명 기반 계정별 개수를 계산하고, 계정별 2개 이상인 row만 표시하도록 했다.
- `manifest.outputs`와 실제 폴더의 `parquet_files`를 합쳐 후보를 계산하게 복구했다. manifest에 없는 같은 계정 Parquet가 폴더에 추가된 경우도 `병합대상 모아보기`에 표시된다.
- 파일명이 이미 `.parquet`로 끝나는 fallback row에서 미리보기 선택값이 `.parquet.parquet`가 되지 않도록 파일명 계산을 공통 helper로 통일했다.
- 메타데이터가 없는 실제 Parquet row는 파일명에서 계정명을 표시하고, 없는 숫자 메타데이터는 `0` 대신 `-`로 표시하게 했다.
- `Quantiwise - Parquet 미리보기`의 `Parquet 모아보기` 명칭은 그대로 유지했다.
- UI 용어 문서와 assets Excel 변환 계약 문서를 갱신했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `rg -n "병합대상 모아보기|Parquet 모아보기|mergeCandidateRowsFromInfo|병합 대상 경로에 표시할 병합 대상" frontend/finiq_GUI/apps/market-desk/src/features/assets-excel/AssetExcelUtilityView.tsx docs PLANS.md`.
- Passed after restore: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed after screenshot fix: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-18 Quantiwise 병합 동일 폴더 및 정리 설정

## Purpose
- `Quantiwise - 병합하기`의 병합 대상 경로 설명 문구를 제거한다.
- 시스템 설정에 `동일 폴더에서 작업하기`와 `병합된 요소 정리하기`를 추가해 병합 위치와 성공 후 정리 동작을 제어한다.

## Implementation Summary
- `동일 폴더에서 작업하기` 기본값은 `false`, `병합된 요소 정리하기` 기본값은 `true`로 설정 저장/로드 경로에 추가했다.
- 병합 요청 payload와 job worker가 두 옵션을 백엔드 병합 함수로 전달하도록 확장했다.
- `동일 폴더에서 작업하기`가 켜지면 실제 출력 경로를 `병합 대상 경로`로 강제하고, `병합된 요소 정리하기`가 켜지면 병합 성공 후 선택된 원본 Parquet 파일을 `병합 대상 경로/merged`로 이동한다.
- 병합 실패 시 원본 파일을 이동하지 않는 regression test를 추가했다.
- 병합 대상 경로 아래 안내 문구를 제거했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/routers/assets_excel.py src/finiq/market_desk/web/routers/config.py src/finiq/market_desk/web/app.py src/finiq/config.py`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_assets_excel.py -k "merge_asset_parquet_outputs" -vv`.
- Passed: `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/market_desk/test_kind_web_app.py -k "asset_excel_directories" -vv`.
- Deep inspection 1회 completed: 요구사항 연결을 diff/검색으로 점검했고, 동일 폴더에서 결과 파일명이 원본과 같은 경우 결과가 정리 폴더로 이동될 수 있는 문제를 발견해 임시 파일 승격 방식으로 수정했다.

# 2026-06-18 Quantiwise 병합 다중 2파일 묶음

## Purpose
- `Quantiwise - 병합하기`에서 같은 계정 Parquet 파일을 2개씩 여러 묶음으로 선택해 한 번에 병합할 수 있게 한다.
- 병합 결과 Parquet 파일명에도 실제 시작일과 종료일을 포함한다.

## Implementation Summary
- 병합 선택 검증을 `정확히 2개`에서 `계정별 정확히 2개`로 확장했다.
- 서로 다른 계정 파일 1개씩만 고른 교차 선택은 API와 UI에서 실행되지 않게 했다.
- 병합 결과 파일을 `<accountName>_<YYYYMMDD>_<YYYYMMDD>.parquet` 형식으로 저장하고 manifest 계정 payload에 `output_file`을 추가했다.
- 병합 화면은 같은 계정당 최대 2개까지 선택할 수 있고, 모든 선택 계정이 2개씩 갖춰졌을 때만 실행 버튼을 활성화한다.
- `docs/assets-excel-conversion.md`의 병합 계약을 계정별 2개 묶음 선택으로 갱신했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/routers/assets_excel.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/test_assets_excel.py -k "merge_asset_parquet_outputs"`.
- Passed: `python3 -m pytest tests/test_assets_excel.py`.
- Passed: `python3 -m pytest tests/market_desk/test_server.py`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `npm run build -w @finiq/app-market-desk --` from `frontend/`.
- Failed then corrected: `npm run build -w @finiq/app-market-desk --` from repo root failed because the root has no `package.json`.

# 2026-06-18 Quantiwise 병합 선택 파일만 읽기

## Purpose
- `Quantiwise - 병합하기`에서 `close` 2개만 선택하면 선택하지 않은 account Parquet는 스캔하거나 읽지 않게 한다.
- 병합 로그도 경로 전체 read처럼 보이지 않게 실제 병합 대상만 표시한다.

## Implementation Summary
- 병합 실행 중 `inspect_asset_excel_output(target)`를 호출하지 않게 해 target 경로 전체 Parquet 목록 스캔을 제거했다.
- 선택 파일 2개만 `_existing_account_frames`에 전달하고, account metadata는 manifest에서 필요한 부분만 읽게 했다.
- 선택하지 않은 `adjHigh` 파일이 target 경로에 있어도 `pd.read_parquet` 호출 대상에 포함되지 않는 regression test를 추가했다.
- progress log는 선택 파일 목록과 `Merging close...`만 남기게 했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/app.py src/finiq/market_desk/web/routers/assets_excel.py`.
- Passed: `python3 -m pytest tests/test_assets_excel.py -k "merge_asset_parquet_outputs"`.
- Passed: `python3 -m pytest tests/test_assets_excel.py`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-18 Quantiwise 병합 2개 파일 선택

## Purpose
- `Quantiwise - 병합하기`를 경로 안의 여러 파일 일괄 병합이 아니라 Parquet 파일 2개 선택 병합으로 제한한다.
- UI에서 선택 수를 명확히 보여주고, 2개를 선택하지 않으면 실행하지 않게 한다.

## Implementation Summary
- 병합 화면의 `Parquet 모아보기` 표에 선택 체크박스를 추가하고 최대 2개까지만 선택되게 했다.
- 병합 실행 payload에 `selected_files`를 추가하고, 프론트엔드와 백엔드 모두 정확히 2개 선택을 검증하게 했다.
- 백엔드 병합 로직은 `병합 대상 경로` 전체가 아니라 선택된 2개 Parquet 파일만 읽어 결과를 생성하게 했다.
- 병합 완료 로그는 변환 완료가 아니라 병합 완료로 표시되게 분기했다.
- `docs/assets-excel-conversion.md`에 2개 파일 선택 병합 계약을 기록했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/routers/assets_excel.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/test_assets_excel.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py -k "asset_excel_directories"`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `npm run build -w @finiq/app-market-desk --`.
- Checked: existing dev server at `http://127.0.0.1:3000/utility/assets-excel/merge` rendered the page title, target/output path fields, two-file selection guidance, selected-file count, Parquet table, and disabled run button with zero selected files.

# 2026-06-18 공시원문 목차 분리 단순화

## Purpose
- KIND 내부 HTML 목차 분리를 특정 목차 선택/렌더링 흐름이 아니라 파일별 전체 목차 분리 흐름으로 정리한다.
- 불필요한 preview/list/render API와 샘플/렌더링 UI를 제거하고, 문서별 목차 스캔과 저장 job 상태만 남긴다.

## Implementation Summary
- `/api/disclosures/html/sections/list`, `/preview`, `/render` 라우트와 관련 프론트 호출을 제거했다.
- 스캔 결과는 문서별 목차 목록, 목차 없음 수, 읽기 실패 수, 통합 문제 파일 목록만 반환하게 했다.
- 문제 파일 표시 수와 최대 처리 건수는 우측 설정 버튼에서 조정하게 했다.
- 목차 저장 job은 선택 목차 없이 각 HTML의 모든 `toc_N` 섹션을 `결과 경로/<toc_id>/<원본 파일명>.html` 구조로 저장하게 했다.
- `h2 id="toc_N"`가 없는 옛 KIND 내부 HTML은 `body` 직계 `P.SECTION-1`을 fallback 목차로 사용해 `toc_1`, `toc_2`처럼 분리하게 했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/market_desk/web/disclosure_html_sections.py src/finiq/market_desk/web/routers/workflows.py`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_service.py -k "html_sections or html_parse_modes"`.
- Passed: `python3 -m pytest tests/market_desk/test_kind_web_app.py -k "html_section"`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-17 페이지 이동 후 실행 로그 복구

## Purpose
- 실행 중인 백엔드 job이 있는데도 다른 페이지로 이동했다가 돌아오면 실행 로그가 사라지는 문제를 해결한다.

## Implementation Summary
- `useJobPolling`이 시작한 job id를 페이지 경로와 polling endpoint 기준으로 `sessionStorage`에 저장하게 했다.
- 페이지 재진입 시 저장된 job id로 polling을 재개해 백엔드의 `progress_log`를 다시 표시하게 했다.
- 페이지 언마운트 시 pending timeout을 정리하고, 완료/실패/중단 또는 stale job 404에서는 저장된 job id를 제거하게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- 

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

# 2026-06-18 Quantiwise 병합 직사각형 검증

## Purpose
- `Quantiwise - 병합하기`에서 두 Parquet 경로를 합칠 때 결과가 구조적으로 완전한 날짜/종목코드 직사각형인 경우만 허용한다.
- 날짜축 병합은 구간이 겹치거나 종료일/시작일이 하루 차이로 붙는 경우만 허용한다.

## Implementation Summary
- 계정별 병합 전에 입력 Parquet들의 날짜별 종목코드 coverage를 검사해 partial table이 생기면 병합을 중단하게 했다.
- 날짜 구간들이 겹치거나 하루 차이로 이어지지 않으면 같은 종목코드 집합이어도 병합을 거절하게 했다.
- 같은 계정의 Parquet 파일이 한 입력 경로에 여러 개 있을 때 첫 파일만 읽던 문제를 고쳐 모두 병합 후보에 포함하게 했다.
- 병합 규칙을 `docs/assets-excel-conversion.md`에 기록했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py`.
