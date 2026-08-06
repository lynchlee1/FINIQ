## 2026-08-06 — Guide·Cases·Reference 분류를 전체 문서에 적용

### Purpose

- `02-table`에서 확정한 문서 경계를 나머지 `docs/` 하위 모듈에도 적용한다.
- 정상 기능은 Guide에서 빠짐없이 찾을 수 있게 하고, 조건부 동작과 정적 조회 사실은 각각 Cases와 Reference가 맡게 한다.

### Implementation summary

- 기존 `behavior.md`를 없애고 조건, 지원 변형, 복구, 한계와 중단 규칙을 `cases.md`로 옮겼다.
- 기존 정상 동작의 기능 제목과 입력→결과 흐름을 `guides.md`에 합쳤다. 조건문만 Cases로 분리하고 경로, 식별자, 자료 형식, 상태와 상수는 Reference에 남겼다.
- `07-html-parse`의 mode·유무상증자 하위 문서와 Ontology 문서도 같은 기준으로 다시 나눴다.
- 모든 README 색인과 교차 링크를 Guide·Cases·Reference 파일명에 맞게 갱신했다.

### Verification result

- `docs/`의 Guide 26개, Cases 24개, Reference 22개를 확인했고 `behavior.md`와 Behavior 링크는 남지 않았다.
- 이전 문서의 inline code 용어와 세부 기능 제목이 새 모듈 문서에서 계속 확인되는지 대조했다.
- Markdown 78개가 모두 `docs/README.md`에서 도달하며 끊어진 로컬 링크와 빈 H2·H3 절이 없는지 확인했다.
- 모듈 안의 문서 유형 사이에 긴 본문 문장이 그대로 중복되지 않는지 검사했다.
- `git diff --check`를 통과했다. 문서만 바꿨으므로 runtime 시험은 하지 않았다.

<!-- HUMANIZE-SUMMARY
원본 877자 / 윤문본 877자 / 변경률 0.00%
탐지: S1 0→0, S2 0→0
자체검증: 6/6 통과
등급: B — S1·S2 패턴은 없으나 의미 불변 원칙에 따라 고칠 문장이 없어 A 등급의 변경률 조건에는 들지 않음.
주요 변경: 없음 — 기술 문서의 간결한 문장과 고유명사·수치·경로를 그대로 보존함.
-->
