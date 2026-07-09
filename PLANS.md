# Completed Changes

## 2026-07-09 공시원문 변환 공통 fallback 문서 갱신

- Purpose: fallback 제거 후 현재 공시원문 변환 로직만 설명하도록 공통 HTML 파서 규칙 문서를 최신화한다.
- Implementation: `common-html-parser-logic-rules.md`의 fallback 최소화 원칙에 사용자 승인 규칙을 추가하고, metadata 탐색/병합, `rcept_no` 제거, 최상위 `families` 저장, source preview, change-log 비교 필드, 사채발행/유무상증자에 남아 있는 허용 fallback을 현재 코드 기준으로 정리했다.
- Verification: 관련 코드와 문서 검색으로 `kind_disclosure_html_manifest.json`, `rcept_no`, 정정공시 묶음, `CHANGE_LOG_COMPARISON_FIELDS`, source preview 계약을 대조했다. 문서 변경만 수행하여 테스트는 실행하지 않았다.

## 2026-07-09 공시원문 변환 fallback 최소화

- Purpose: 결과 영향이 없는 것으로 확인된 metadata 병합 우선순위와 change-log record 전체 필드 탐색 fallback을 제거하고, 정정공시 묶음 저장 구조를 record 반복 저장에서 최상위 저장으로 바꾼다.
- Implementation: `_merge_metadata_index`의 병합 우선순위 옵션을 제거하고, change-log 비교 필드는 모드별 `CHANGE_LOG_COMPARISON_FIELDS`만 사용하도록 정리했다. parsed JSON은 정정공시 묶음 전체를 최상위 `families`에 저장하고, 각 record에는 `family_id`/`current_sequence`/`family_member_count` 참조 필드만 저장하도록 변경했다. summary, change-log, preview, export, 공통 HTML 파서 규칙 문서, 관련 테스트 fixture를 새 저장 계약에 맞췄다.
- Verification: `python3 -m pytest tests/market_desk/test_kind_web_service.py -q` 통과(401 passed). 병합 우선순위 옵션, 동적 필드 탐색 helper, record 전체 필드 탐색 fallback, 과거 change-log 상수명이 관련 코드에 남지 않았음을 확인했다.
