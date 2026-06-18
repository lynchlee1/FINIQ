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
