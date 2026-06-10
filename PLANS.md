## 2026-06-10 공시원문 분할저장 구조 전환 박스

- 목적: 공시원문 외부 저장/내부 저장 화면에서 이미 저장된 HTML 파일을 재다운로드 없이 일반 폴더와 연도별 분할저장 폴더 구조 간 전환할 수 있게 한다.
- 구현: 기존 `run_partition_storage_payload`에 `move` 옵션을 추가해 복사/이동 결과를 구분할 수 있게 했다. 외부/내부 HTML 저장 공통 화면에 "분할저장 구조 전환" 카드를 추가했다.
- 리뷰 수정: 분할저장 구조 전환 성공 후 기존 폴더 감지 상태가 stale 될 수 있어, 성공 결과의 `mode`에 맞춰 저장 분할 토글을 갱신하고 동일 경로라도 기존 폴더 검사를 강제로 다시 실행하도록 했다.
- 안전 수정: 덮어쓰기 옵션을 화면에서 제거했다. 전환 작업은 입력 경로와 출력 경로를 별도로 받고, 출력 경로에 복사 저장한 뒤 공시원문 기존 저장 검사로 대상 파일 수/누락/대상 외 파일/분할 구조를 확인한다. 누락이 있으면 한 번 더 복사 보정을 시도하고, 대상 외 파일이나 구조 불일치처럼 안전하게 고칠 수 없는 문제는 오류로 출력한다. 무결성 검사가 통과한 경우에만 출력 경로를 현재 저장 경로로 반영한다.
- 설정 JSON: 무결성 검사가 통과한 출력 경로에 `kind_disclosure_html_manifest.json`을 작성하는 API를 추가했다. 외부 저장 전환은 필터 JSON 기준, 내부 저장 전환은 외부 저장 폴더 manifest 기준으로 작성한다.
- 검증: `pytest tests/market_desk/test_partition_utility.py tests/market_desk/test_kind_web_service.py::test_write_disclosure_html_manifest_payload_from_source_json_path tests/market_desk/test_kind_web_service.py::test_write_disclosure_html_manifest_payload_from_external_directory_manifest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui -q` 통과. `npm run build -w @finiq/app-market-desk` 통과.
