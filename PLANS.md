# Completed Changes Requiring Follow-up

## 2026-08-14: shareholder-meeting entity and relationship extraction

- Purpose: turn shareholder-meeting notices and results into evidence-backed people, organizations, agendas, and phase-aware relationships without treating candidates as current officers or inferring unnamed parties.
- Unresolved finding: the final production snapshot has not been rerun over all 71,965 historical pairs, so earlier full-history totals are superseded and must not be presented as current verification. Free-text extraction remains deliberately high-precision rather than exhaustive; ambiguous career statements, unknown proposal wording and unnamed or implicit transaction counterparties are not inferred. Person resolution remains issuer-scoped, and ShareholderMeeting identity remains disclosure-scoped, so separate NOTICE and RESULT receipts for the same physical meeting are not merged automatically.

## 2026-08-29: 06 목차 분리 실행 결과에 전체 목차 구조 표시

- Purpose: 06 `공시원문 목차 분리` 실행이 완료된 뒤, 실행한 전체 입력에서 실제로 확인한 모든 고유 목차 구조와 구조별 목차 수·공시 수를 화면에 표시한다.
- Implementation summary: 저장 과정에서 이미 파싱한 목차 구조를 입력 순서대로 집계해 `section_patterns`로 반환하고, 고유 구조와 최대 3개 샘플만 보관해 메모리 사용량이 문서 수에 비례하지 않도록 했다. 화면은 성공한 저장 응답을 받은 뒤에만 `목차 구조 종류` 카드를 렌더링한다. 각 구조는 내부 `signature`, `preamble`, `toc_N` 문자열 대신 `머리말`, `표지`, `부`, `N단계 목차`, `본문`과 제목을 줄 단위·위계별 들여쓰기로 표시하고, 실제 목차 수와 비목차를 포함한 전체 구간 수를 분리한다. 실행 시 제외되는 정정 구간은 응답의 `will_remove` 판정값으로 해당 줄에 `제거 예정` 배지를 표시한다. 관련 UI 용어와 06단계 문서도 같은 계약으로 갱신했다.
- Verification result: 관련 백엔드 테스트 47개, 전체 프런트엔드 테스트 203개, Market Desk production build와 TypeScript 검사를 통과했다. 저장 결과가 서로 다른 구조 2종을 모두 반환하고 정정 머리말에만 `will_remove=true`를 반환하는 회귀 테스트, 완료 응답이 전체 구조 카드와 `제거 예정` 표시를 연결하는 프런트엔드 테스트를 추가했다.
