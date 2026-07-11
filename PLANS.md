# Completed Changes

## 2026-07-11 — 제한된 HTML parser 공통 helper 정리

- 목적: 번호 label 정규화가 실제 사채발행 `납입일` 형식을 정확히 지원하게 하고, 제한된 공통 helper의 실제 사용처를 문서에서 추적하며, 사용되지 않는 숫자 변환 helper를 제거한다.
- 구현: 공백 제거 후 `숫자.`와 `숫자-숫자.`까지만 label 번호로 허용하고 더 깊은 번호는 제외했다. `row_with_label()`과 `parse_ints()`의 실제 parser·field·column 사용처 및 호출부 변경 시 문서 동기화 규칙을 공통 로직 문서에 추가했다. 저장소 내부 호출이 없는 `parse_float()`와 공통 export를 제거했다.
- 검증: 번호 label과 배정주식수 다중 수량 관련 회귀 테스트 9개가 통과했다. 변경한 공통 Python 모듈의 `py_compile`과 `git diff --check`도 통과했으며, `parse_float`의 실행 코드·공통 export·parser 문서 참조가 남아 있지 않음을 확인했다.

## 2026-07-11 — HTML parser 경고와 record 저장 필터 분리

- 목적: 업무 필터에서 제외된 record에도 원천 누락 같은 파싱 경고가 있으면 최종 payload에서 확인할 수 있게 한다.
- 구현: 단일·병렬 parsing 모두 parser warning을 record filter보다 먼저 수집한다. filter는 `records[]` 포함 여부만 결정하고 `warnings[]`와 `warning_report_counts`에는 영향을 주지 않도록 공통 처리 순서와 문서를 변경했다. 파싱 예외로 record를 만들지 못한 파일은 기존대로 `errors[]`에 기록한다.
- 검증: record filter를 통과한 1건만 `records[]`에 저장하면서 입력 3건의 warning을 모두 유지하는 회귀 테스트를 worker 1개와 2개 실행에서 확인했다. 관련 비리소스 backend 테스트 90개, 변경 Python 모듈 `py_compile`, parser 문서 상대 링크, `git diff --check`도 통과했다.

## 2026-07-11 — HTML parser 경고 수집 fallback 제거

- 목적: 실제 parser가 만드는 `parse_warnings`와 정확히 하나의 수준별 목록 조합만 허용하고, 실제 자료에서 발생하지 않는 수준 우선순위·누락 수준 보정·기본 수준 대체 로직을 제거한다.
- 구현: `parse_warnings`의 순서와 수준별 목록의 수준을 결합해 payload 경고를 한 번씩 만들도록 단순화했다. 비어 있는 경고, 목록 내부 중복, 수준 누락, 복수 수준, 양쪽 목록 불일치, 지원하지 않는 수준은 보정하지 않고 warning 계약 위반 오류로 처리한다. 공통 예외 처리 문서도 같은 계약만 남기도록 축약했다.
- 검증: 실제 `resources/KIND/bond_issuance` HTML 15,175건의 경고 2,033개와 `resources/KIND/rights_issuance` HTML 19,975건의 경고 4,642개를 현재 parser와 실제 metadata로 전수 확인했다. 35,150건 모두 새 계약을 통과했고 최종 경고 중복과 parsing 실패는 0건이었다. 관련 비리소스 backend 테스트 89개, 변경 Python 모듈 `py_compile`, parser 문서 상대 링크, `git diff --check`도 통과했다.
