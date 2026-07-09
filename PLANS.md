# Completed Changes

## 2026-07-09 공시원문 변환 source fallback 정리

- Purpose: 공시원문 변환에서 wrapper/body 복원과 source preview 파일 탐색 fallback을 줄이고, 테스트 fixture를 metadata 부모 디렉토리 계약에 맞춘다.
- Implementation: common HTML parser의 wrapper body lookup/preserve helper export를 제거하고, summary source lookup은 `source_directory/<acpt_no>.html` 또는 `source_directory/<YYYY>/<acpt_no>.html`의 정확한 파일명만 확인하도록 제한했다. 공통 parser 규칙 문서를 현재 source preview 계약에 맞추고, 관련 테스트 fixture의 `filtered.json`/`compressed-external-html.json` 위치를 입력 디렉토리 부모로 옮겼다.
- Verification: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` 통과(401 passed).

## 2026-07-09 공시원문 변환 회사명 SoC 고정

- Purpose: `corp_name` 보강을 `filtered.json.company_name` 단일 출처로 고정하고, `compressed-external-html.json` 또는 `header` 기반 회사명 fallback을 제거한다.
- Implementation: HTML parse metadata 탐색을 입력 디렉토리의 한 단계 위 디렉토리로 고정하고, `filtered.json` 로드에서만 `company_name`을 읽도록 분리했다. `compressed-external-html.json` 로드는 정정 family/doc metadata만 보강하며 회사명은 읽지 않는다. preview/filter 후보 metadata 로드 호출부와 공통 파서 규칙 문서를 같은 계약으로 맞췄다.
- Verification: `python3 -m py_compile src/finiq/market_desk/web/features/disclosures/html_parse_common.py src/finiq/market_desk/web/features/disclosures/html_parse_preview.py` 통과. 실제 `resources/KIND/bond_issuance/kind_html_contents_grouped_sections` 15,175건과 `resources/KIND/rights_issuance/kind_html_contents_sections` 19,975건 기준으로 metadata 회사명이 모두 채워지는 것을 확인했고, 문제 예시 `20080924000347`, `20111216000861`, `20150513000264`, `20171228000858`의 `corp_name`이 각각 `filtered.json.company_name` 값으로 반영되는 것을 확인했다.

## 2026-07-09 공시원문 변환 fallback 최소화

- Purpose: 결과 영향이 없는 것으로 확인된 metadata 병합 우선순위와 change-log record 전체 필드 탐색 fallback을 제거하고, 정정공시 묶음 저장 구조를 record 반복 저장에서 최상위 저장으로 바꾼다.
- Implementation: `_merge_metadata_index`의 병합 우선순위 옵션을 제거하고, change-log 비교 필드는 모드별 `CHANGE_LOG_COMPARISON_FIELDS`만 사용하도록 정리했다. parsed JSON은 정정공시 묶음 전체를 최상위 `families`에 저장하고, 각 record에는 `family_id`/`current_sequence`/`family_member_count` 참조 필드만 저장하도록 변경했다. summary, change-log, preview, export, 공통 HTML 파서 규칙 문서, 관련 테스트 fixture를 새 저장 계약에 맞췄다.
- Verification: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` 통과(401 passed). 병합 우선순위 옵션, 동적 필드 탐색 helper, record 전체 필드 탐색 fallback, 과거 change-log 상수명이 관련 코드에 남지 않았음을 확인했다.
