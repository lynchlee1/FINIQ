# Completed Changes

## 2026-07-11 — 개별 HTML parser 직접 반환값 설명 개선

- 목적: `common-html-parser-data-structure.md`의 개별 parser 직접 반환값 설명을 고등학생도 이해할 수 있는 수준으로 명확하게 작성한다.
- 구현: 직접 반환값의 의미와 생성 과정을 쉬운 문장으로 풀어 쓰고, 조건부 warning·상태 필드 및 포함·제외 필드를 표로 정리했다.
- 검증: 기존 필드명과 포함 조건을 유지했는지 확인하고 문서 diff를 검토했다.
