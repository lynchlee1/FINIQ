# 2026-06-12 압축 외부 HTML JSON 분할저장 메타데이터 제거

## Purpose
- `compressed-external-html.json`이 `split_by_year`, `input_split_by_year`, `output_split_by_year`를 저장하지 않게 한다.
- "공시원문 내부 저장 설정"의 "기존 메타데이터 기준으로 설정 맞추기" 버튼을 폴더 입력과 JSON 파일 입력 모두에서 제거한다.

## Implementation Summary
- 외부 HTML 압축 산출물과 압축 결과 응답에서 `split_by_year`, `input_split_by_year`, `output_split_by_year` 필드를 제거했다.
- 내부 저장 기존 확인 API가 압축 JSON의 `split_by_year`를 저장 경로 분할저장 fallback으로 쓰지 않게 했다.
- 기존 저장 구조 불일치 판단은 저장 경로 폴더 구조에서 감지된 값만 사용하게 했다.
- 내부 저장 UI에서 "기존 메타데이터 기준으로 설정 맞추기" 버튼과 핸들러를 제거했다.
- 불일치 경고는 버튼 안내 대신 저장 경로의 `분할저장 On/Off`를 직접 맞추라는 문구로 바꿨다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k 'compress_disclosure_external_html_payload or check_disclosure_html_output_directory_ignores_compressed_json_split_by_year or check_disclosure_html_output_directory_prefers_output_directory_split_by_year or html_parse_modes_are_registered_documented_and_listed_in_ui'`.
- Passed: `pytest tests/market_desk/test_kind_web_app.py -k 'html_content_download_check_existing_route_ignores_compressed_json_split_by_year or html_content_download_check_existing_route_prefers_output_directory_split_by_year or html_content_download_check_existing_route_honors_split_options'`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-12 기존 메타데이터 맞춤 저장 경로 분할저장 한정

## Purpose
- "공시원문 내부 저장 설정 > 기존 메타데이터 기준으로 설정 맞추기"가 다른 입력 설정이 아니라 "저장 경로"의 분할저장 On/Off만 맞추게 한다.

## Implementation Summary
- 기존 메타데이터 mismatch 판단을 `detected_output_split_by_year`와 `downloadSplitByYear` 비교로 한정했다.
- 버튼 핸들러가 `setDownloadSplitByYear(...)`만 호출하고 `contentSourceSplitByYear`는 건드리지 않게 했다.
- 정적 UI 테스트가 버튼 핸들러에서 `setContentSourceSplitByYear`를 호출하지 않는지 확인하게 했다.
- 저장 경로의 기존 폴더 구조가 감지되면 그 값을 압축 JSON의 `split_by_year`보다 우선하도록 했다.
- 저장 경로에서 분할저장 구조를 감지할 수 없을 때만 압축 JSON의 `split_by_year`를 fallback으로 사용한다.
- 비-JSON 오류 응답을 `response.json()`으로 강제 파싱하지 않게 해 `Unexpected token 'I'... is not valid JSON` UI 오류를 제거했다.
- 기존 확인/폴더 검사에서는 압축 JSON의 `doc_no` 선택지 스캔을 생략하고 접수번호/연도만 읽는 빠른 경로를 사용하게 했다.
- 존재하지 않는 대상 HTML 경로에 반복 `resolve()`를 호출하지 않게 해 큰 폴더 재확인 시간을 줄였다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k 'check_disclosure_html_output_directory_uses_compressed_json_split_by_year or check_disclosure_html_output_directory_prefers_output_directory_split_by_year or html_parse_modes_are_registered_documented_and_listed_in_ui'`.
- Passed: `pytest tests/market_desk/test_kind_web_app.py -k 'html_content_download_check_existing_route_uses_compressed_json_split_by_year or html_content_download_check_existing_route_prefers_output_directory_split_by_year or html_content_download_check_existing_route_honors_split_options'`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k 'check_disclosure_html_output_directory or clean_disclosure_html_output_directory or compressed_external_json or compress_disclosure_external_html_payload or download_disclosure_html_contents_payload_prefers_compressed_external_json or download_disclosure_html_contents_payload_reads_compact_docs_json'`.
- Passed: `pytest tests/market_desk/test_kind_web_app.py -k 'html_content_download'`.
- Direct checked the first screenshot path pair: existing check completed successfully in about 4.3 seconds.
- Browser checked `http://localhost:3000/html-content-download`: with backend running, JSON file input shows the existing range panel without `Internal Server Error`; manually toggling storage split On and pressing "기존 메타데이터 기준으로 설정 맞추기" changes the storage-path split button back to Off.

# 2026-06-12 공시원문 압축 JSON 경로 제거 및 JSON 입력 설정 맞춤

## Purpose
- "공시원문 외부 저장 > 외부 HTML 압축" 산출물인 `compressed-external-html.json`이 로컬 절대 경로를 저장하지 않게 한다.
- "공시원문 내부 저장 > JSON 파일 입력"에서 "기존 메타데이터 기준으로 설정 맞추기"가 압축 JSON의 `split_by_year` 기준으로 동작하게 한다.
- JSON 파일 입력 도움말의 압축 파일 안내문을 제거한다.

## Implementation Summary
- `finiq_disclosure_external_html_docs_v1` 산출물에서 `input_directory`, `output_directory`, `output_path` 저장을 제거하고 `format`, `split_by_year`, `summary`, `records` 중심 스키마를 유지했다.
- 내부 저장 기존 확인 API가 `source_compressed_json_path` 입력을 받을 때 압축 JSON의 `split_by_year`를 `detected_output_split_by_year`와 검사 payload에 반영하게 했다.
- 프론트엔드는 기존 확인 응답에 분할저장 메타데이터가 있으면 기존 저장 파일이 없어도 설정 맞추기 패널을 표시하고, JSON 파일 입력 도움말 문구를 비웠다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k 'compressed_external_json or compress_disclosure_external_html_payload or html_parse_modes_are_registered_documented_and_listed_in_ui'`.
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k 'check_disclosure_html_output_directory or clean_disclosure_html_output_directory or download_disclosure_html_contents_payload_accepts_compressed_json_file'`.
- Passed: `pytest tests/market_desk/test_kind_web_app.py -k 'html_content_download'`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Direct checked a generated compressed JSON: `format=finiq_disclosure_external_html_docs_v1`, no path keys, and JSON input existing-check applied `split_by_year`.

# 2026-06-12 공시원문 내부 저장 JSON 입력 메타데이터 맞춤 재수정

## Purpose
- "공시원문 내부 저장"의 JSON 파일 입력에서 "기존 메타데이터 기준으로 설정 맞추기"를 눌러도 분할저장 설정 불일치가 계속 남는 문제를 고친다.

## Implementation Summary
- JSON 파일 입력 모드에서는 소스 폴더 분할저장 설정을 비교하지 않도록 `existingSplitMismatch` 조건을 폴더 입력 모드로 제한했다.
- 출력 폴더 분할저장 설정은 기존처럼 기존 메타데이터 기준으로 맞춘다.
- UI 정적 테스트가 JSON 파일 입력에서 소스 분할저장 mismatch를 보지 않는 조건을 확인하게 했다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k html_parse_modes_are_registered_documented_and_listed_in_ui`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-12 UI 용어집 추가 및 공시원문 용어 통일

## Purpose
- UI 버튼명과 기능명이 페이지마다 다르게 생성되지 않도록 기준 용어를 문서화한다.
- 공시원문 HTML 저장/압축/병합 화면의 최근 추가 문구를 기존 로그와 화면 용어에 맞춘다.

## Implementation Summary
- `docs/ui-terminology.md`에 공시원문 HTML 워크플로우 용어집을 추가했다.
- `AGENTS.md`에 UI 문구 변경 전 용어집을 확인하고, 새 용어가 필요하면 같은 변경에서 용어집과 UI/test를 함께 맞추라는 규칙을 추가했다.
- "문서 JSON 압축"은 "외부 HTML 압축"으로, "내부 HTML JSON 병합"은 "내부 HTML 병합"으로 통일했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k html_parse_modes_are_registered_documented_and_listed_in_ui`.

# 2026-06-12 공시원문 내부 HTML 병합 모드 분리

## Purpose
- "공시원문 내부 저장"의 내부 HTML 병합 기능을 외부 저장의 외부 HTML 압축 기능처럼 상단 별도 선택 모드로 분리한다.

## Implementation Summary
- 내부 저장 화면에 `contentTaskMode`를 추가해 "내부 HTML 저장"과 "내부 HTML 병합"을 상단 토글로 전환하게 했다.
- 내부 HTML 저장 모드에서만 저장 경로/기존 폴더 확인/실행 카드가 보이게 하고, 내부 HTML 병합 모드에서는 병합 카드만 보이게 했다.
- 내부 HTML 병합 모드의 사이드 설정은 병합 payload에 쓰이는 테스트 옵션만 표시하게 했다.
- UI 정적 테스트에 내부 저장 상단 모드 상태와 라벨 확인을 추가했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k html_parse_modes_are_registered_documented_and_listed_in_ui`.

# 2026-06-12 공시원문 내부 저장 JSON 입력 설정 적용 수정

## Purpose
- "공시원문 내부 저장 설정"의 JSON 파일 입력에서 "기존 메타데이터 기준으로 설정 맞추기" 버튼이 기존 저장 구조의 분할저장 설정을 적용하지 못하는 문제를 고친다.
- "폴더 입력"과 "JSON 파일 입력" 토글 버튼 사이에 아주 작은 간격을 둔다.

## Implementation Summary
- 기존 대상이 모두 저장된 상태여도 버튼이 기존 메타데이터 감지값을 적용하도록 no-op 반환을 제거했다.
- JSON 파일 입력에서는 소스 폴더 분할저장 설정이 없으므로 출력 폴더 분할저장 설정만 적용하고, 폴더 입력일 때만 소스 분할저장 설정을 맞추도록 제한했다.
- 내부 저장의 입력 모드 토글에 `gap-1`을 추가했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k html_parse_modes_are_registered_documented_and_listed_in_ui`.

# 2026-06-12 공시원문 내부 저장 폴더 검사 개선

## Purpose
- "공시원문 내부 저장 설정"에서 폴더 검사가 오래 걸리는 문제를 줄인다.
- 폴더 검사 완료 후 삭제 후보가 0건이어도 검사 결과 박스가 유지되게 한다.

## Implementation Summary
- 내부 저장 폴더 검사/기존 파일 확인용 소스 스캔을 추가해 외부 HTML의 `docNo` 파싱을 피하고, 파일명/매니페스트/압축 JSON만으로 대상 접수번호와 연도를 계산한다.
- 실제 내부 HTML 다운로드 경로는 기존처럼 `docNo`를 파싱하므로 실행 동작은 유지한다.
- 프론트엔드에서 실행 결과 상태와 폴더 검사 결과 상태를 분리해 검사 결과 알림이 사라지지 않도록 했다.
- 기존 폴더 자동 재확인 실패 시 기존 안내/검사 결과를 지우지 않고, 실패 메시지만 별도로 표시한다.
- 자동 재확인 요청을 매번 abort하지 않도록 해 Next 프록시의 `socket hang up` 로그와 박스 깜빡임을 줄였다.
- 이번 대상이 모두 저장된 상태에서는 "기존 메타데이터 기준으로 설정 맞추기" 버튼은 유지하되, 핸들러를 no-op 처리해 불필요한 재확인을 막았다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_app.py -k "html_content_download_inspect_folder or html_content_download_check_existing"`.
- Passed: `npx tsc --noEmit -p finiq_GUI/apps/market-desk/tsconfig.json`.
- Failed after compile/type check: `npm run build --workspace @finiq/app-market-desk` hit Turbopack page-data `PageNotFoundError` for unrelated app routes such as `/graph` and `/html-bond-summary`.

# 2026-06-12 공시원문 저장 폴더 확인 병렬화

## Purpose
- "기존 원문 저장 폴더 확인 중..." 단계가 대상 접수번호가 많을 때 순차 파일 존재 확인으로 느려지는 문제를 줄인다.
- 사용자가 별도 워커 수를 입력하지 않아도 대상 수와 CPU 수 기준으로 자동 병렬 확인을 사용하게 한다.

## Implementation Summary
- 공시원문 HTML 저장 폴더 검사에서 대상 HTML 경로 존재 여부를 자동 산정된 `ThreadPoolExecutor` 워커로 확인한다.
- 대상이 1건이면 스레드풀을 만들지 않고 기존처럼 순차 확인한다.
- UI 상태 문구를 자동 병렬 확인 중임을 알 수 있게 조정했다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k "check_disclosure_html_output_directory or kind_web_ui_links_disclosure_workflows"`.

# 2026-06-12 공시원문 기존 저장 감지 UI 통일

## Purpose
- 공시원문 저장 화면의 기존 저장 감지 UI를 `/download` 페이지의 "기존 다운로드 시도 범위 감지됨" 패널과 같은 구조와 시각 톤으로 맞춘다.
- 새 에셋이나 별도 디자인 패턴을 만들지 않고 기존 카드/버튼/상태 배지 스타일을 재사용한다.

## Implementation Summary
- 기존 원문 저장 감지 패널에 `/download`와 같은 외곽 패널, 헤더 구분선, 재확인 배지, 오른쪽 CTA 버튼, 상태 행, 경고/알림 박스 구조를 적용했다.
- 공시원문 저장 데이터에 맞춰 날짜 범위 대신 저장됨/대상/신규 저장/대상 외 파일 수 요약을 같은 위치에 표시한다.
- 저장 상태, 폴더 검사 필요, 분할저장 설정 불일치를 기존 다운로드 패널의 teal/amber/rose 배지 톤으로 표시한다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k "check_disclosure_html_output_directory or html_parse_modes_are_registered_documented_and_listed_in_ui"`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Browser checked `http://localhost:3001/html-download`: page and updated loading state render without layout errors; the actual existing-data panel was not visible because the live existing-check request was still in progress.

# 2026-06-12 공시원문 압축 JSON 입력 안내 개선

## Purpose
- 공시원문 내부 저장의 JSON 파일 입력에 압축 산출물이 아닌 필터 결과 JSON을 넣었을 때 원인을 명확히 안내한다.
- 내부 저장 파일 입력이 받는 파일이 `compressed-external-html.json`임을 UI에서 명확히 표시한다.

## Implementation Summary
- 내부 저장 파일 입력 라벨/도움말을 압축 JSON 전용으로 되돌려 필터 결과 JSON을 선택하지 않도록 했다.
- 백엔드는 기존처럼 `records`가 있는 압축 JSON만 내부 저장 파일 입력으로 받는다.
- `records`가 없는 JSON을 넣으면 영어 내부 오류 대신 압축 결과 파일을 선택하라는 한국어 안내 오류를 반환한다.

## Verification
- Passed: `pytest tests/market_desk/test_kind_web_service.py -k "accepts_compressed_json_file or compress_disclosure_external_html_payload_writes_compact_json or compress_disclosure_external_html_payload_reads_split_input or compress_disclosure_external_html_payload_accepts_parallel_workers or html_parse_modes_are_registered_documented_and_listed_in_ui"`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Checked existing resources: all discovered `compressed-external-html.json` files contain a `records` list.
