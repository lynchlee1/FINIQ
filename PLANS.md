# Review Findings

## 2026-07-06 공시원문 변환 출력 디렉터리 계약 정리

- Purpose: `공시원문 변환`에서 입력/출력 경로 자동생성을 제거하고, 사용자가 지정한 출력 디렉터리 아래에만 `parsed-{mode}.json`을 쓰도록 경로 계약을 단순화한다.
- Implementation: 변환 페이지의 결과 경로 필드를 파일 저장 경로가 아닌 폴더 경로로 바꾸고, 입력/출력/모드 변경 시 경로를 자동 계산하지 않도록 제거했다. 페이지 진입 시에도 앞 단계가 저장한 `html_section_split_output_directory`와 사용자가 저장한 `html_parse_output_directory`만 읽는다. 실행 API는 `output_directory`를 필수로 받아 `parsed-{mode}.json`을 내부적으로 쓰며, 기존 `output_path` 생략 fallback과 미리보기의 `output_path`/`parse_result_path` result JSON 읽기 분기를 제거했다. 새 설정 키 `html_parse_output_directory`를 추가했다.
- Verification: `node --test tests/frontend/htmlParsePage.test.mjs`; `pytest tests/market_desk/test_kind_web_service.py -k "parse_disclosure_html_payload or build_parse_preview_payload"`; `pytest tests/test_persistence_api.py tests/test_partial_save.py`
- Follow-up: 점이 포함된 출력 디렉터리를 suffix로 오판하지 않도록 기존 파일 경로만 거부하게 수정했고, 발행내역 요약도 파싱 결과 디렉터리 입력을 `parsed-bond_issuance.json`으로 해석하도록 맞췄다. Verification: `pytest tests/market_desk/test_kind_web_service.py -k "dotted_output_directory or bond_parse_summary_payload"`
