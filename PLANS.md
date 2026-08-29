# Completed Changes Requiring Follow-up

## 2026-08-14: shareholder-meeting entity and relationship extraction

- Purpose: turn shareholder-meeting notices and results into evidence-backed people, organizations, agendas, and phase-aware relationships without treating candidates as current officers or inferring unnamed parties.
- Unresolved finding: the final production snapshot has not been rerun over all 71,965 historical pairs, so earlier full-history totals are superseded and must not be presented as current verification. Free-text extraction remains deliberately high-precision rather than exhaustive; ambiguous career statements, unknown proposal wording and unnamed or implicit transaction counterparties are not inferred. Person resolution remains issuer-scoped, and ShareholderMeeting identity remains disclosure-scoped, so separate NOTICE and RESULT receipts for the same physical meeting are not merged automatically.

## 2026-08-29: 06 목차 분리 실행 결과에 전체 목차 구조 표시

- Purpose: 06 `공시원문 목차 분리` 실행이 완료된 뒤, 실행한 전체 입력에서 실제로 확인한 모든 고유 목차 구조와 구조별 목차 수·공시 수를 화면에 표시한다.
- Implementation summary: 저장 과정에서 이미 파싱한 목차 구조를 입력 순서대로 집계해 `section_patterns`로 반환하고, 고유 구조와 최대 3개 샘플만 보관해 메모리 사용량이 문서 수에 비례하지 않도록 했다. 화면은 성공한 저장 응답을 받은 뒤에만 `목차 구조 종류` 카드를 렌더링한다. 각 구조는 내부 `signature`, `preamble`, `toc_N` 문자열 대신 `머리말`, `표지`, `부`, `N단계 목차`, `본문`과 제목을 줄 단위·위계별 들여쓰기로 표시하고, 실제 목차 수와 비목차를 포함한 전체 구간 수를 분리한다. 실행 시 제외되는 정정 구간은 응답의 `will_remove` 판정값으로 해당 줄에 `제거 예정` 배지를 표시한다. 관련 UI 용어와 06단계 문서도 같은 계약으로 갱신했다.
- Verification result: 관련 백엔드 테스트 47개, 전체 프런트엔드 테스트 203개, Market Desk production build와 TypeScript 검사를 통과했다. 저장 결과가 서로 다른 구조 2종을 모두 반환하고 정정 머리말에만 `will_remove=true`를 반환하는 회귀 테스트, 완료 응답이 전체 구조 카드와 `제거 예정` 표시를 연결하는 프런트엔드 테스트를 추가했다.

## 2026-08-29: 01~05 구현 오류 수정 및 04 레거시 의도 보존

- Purpose: 01~05단계 심층 분석에서 확인한 오류 중 01·02·03·05를 수정하고, 04의 넓은 HTML 판별은 과거 KIND HTML 호환을 위한 의도임을 명확히 기록한다.
- Implementation summary: 01 자동 다운로드는 숨김 staging 폴더에서 전체 페이지를 완성하고 checkpoint로 중단 지점부터 재개한다. 모든 페이지 검증 후 첫 페이지를 같은 조건으로 다시 받아 pagination과 공시 행이 같을 때만 기존 결과와 원자적으로 교체하며, 완료 전에는 `kind_workflow.input.json`이나 완료 checkpoint를 게시하지 않는다. 02는 기간 폴더별 pagination 전체 건수와 실제 BODY 행 수를 build·inspection 양쪽에서 대조한다. 03은 닫히지 않은 괄호부터 문자열 끝까지 제거한다. 05는 `selected_main_doc_no`가 `docs`의 유일한 `selected=true` `mainDoc`과 정확히 일치하는지 다운로드 전에 확인하고, 정상 실행의 멤버십 실패 시 기존 manifest를 부분 결과로 덮어쓰지 않는다.
- **04 사용자 직접 명시 의도:** 사용자가 04의 HTML 판별은 과거 HTML 레거시 호환 문제이며 차후 별도로 다룰 것이라고 직접 밝혔다. 따라서 `<html` 일반 문서, `openDisclsViewer` 과거 외부 화면, wrapper 없이 `<P>`로 시작해 `<TABLE>`을 포함하는 과거 본문 조각을 허용하는 현재 규칙은 이번에 오류로 취급하거나 변경하지 않았다. 이 예외 의도를 04 feature/reference와 공통 case 문서에 명시했다.
- Verification result: 전체 Python 테스트 `1529 passed, 167 skipped`, 수정 파일 `py_compile`, `git diff --check`를 통과했다. 추가 회귀 테스트는 실패 다운로드의 입력 metadata 미게시, metadata 게시 실패 시 미완료 checkpoint 유지, 병렬 저장의 최종 페이지 유지, staging 재개·완료 후 게시, 첫 페이지 변경 시 기존 결과 보존, 02 원본 총건수 불일치 거부, 05 선택 문서 불일치 거부와 기존 manifest 보존을 검증한다.
