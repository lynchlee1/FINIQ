# Completed Changes

## 2026-07-11 — HTML parser 공통 예외 처리 계약 개선

- 목적: 완성된 공통 데이터 구조 계약을 유지하면서 상태·경고·오류 규칙을 고등학생도 이해할 수 있는 문장으로 설명한다.
- 구현: 데이터 구조 문서의 형식에 맞춰 짧은 문장, 표, 예시, 의도 순서로 다시 작성했다. 필요한 코드 이름은 백틱으로 표시하고 `record`, `payload`, `parser`, `worker`, `mode`, `limit`, `acpt_no`, `input_directory`를 먼저 정의했다. 정의하지 않은 `workflow`, `metadata`, `filter`, `class`, `message`, `flat` 같은 표현은 쉬운 한국어로 바꾸면서 기존 상태·경고·오류 규칙은 유지했다.
- 검증: 공통 데이터 구조·공통 로직 문서와 파싱 처리 구현을 대조했고 관련 백엔드 테스트 6개가 통과했다. 문서 상대 링크와 `git diff --check`도 통과했으며 `resources/`는 읽거나 변경하지 않았다.
