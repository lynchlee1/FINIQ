# HTML Section Pattern Save Rules Design

## Purpose

`공시원문 목차 분리`에서 모든 HTML 파일을 저장 대상으로 유지하되, 목차 조합별로 저장할 목차만 선택할 수 있게 한다.

## Assumptions

- `목차 조합 모아보기`의 조합 단위는 현재 백엔드가 계산하는 `signature`와 동일하다.
- 결과 폴더 구조는 기존 `결과 데이터 경로/toc_1/...`, `결과 데이터 경로/toc_2/...` 형식을 유지한다.
- 사용자가 조합별 선택을 바꾸지 않으면 기존처럼 해당 조합의 모든 목차를 저장한다.

## User Experience

- `목차 조합 모아보기`의 각 조합 행에 포함 목차 목록을 표시한다.
- 각 목차는 체크박스로 선택한다.
- 기본값은 조합별 모든 목차 선택이다.
- 사용자가 어떤 조합에서 `toc_1`만 선택하면, 그 조합에 해당하는 모든 HTML은 `toc_1`만 저장된다.
- 조합 규칙이 없는 HTML은 기존과 동일하게 모든 목차를 저장한다.

## Backend Behavior

- 목차 조합 요약 응답은 각 조합의 `sections` 목록을 포함한다.
- 목차 저장 시작 payload는 선택 규칙을 받는다.
- 저장 함수는 각 HTML의 조합 `signature`를 계산하고, 해당 signature에 선택 규칙이 있으면 선택된 `toc_id`만 저장한다.
- 선택 규칙에 해당하는 `toc_id`가 없으면 해당 HTML은 저장 파일이 0개일 수 있지만, 읽기 실패나 목차 없음으로 처리하지 않는다.

## Components

- `src/finiq/market_desk/web/disclosure_html_sections.py`: 조합 요약 응답 확장, 저장 규칙 적용.
- `frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx`: 조합별 선택 상태 관리와 저장 payload 전달.
- `frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx`: 조합별 목차 체크 UI 표시.
- `tests/market_desk/test_kind_web_service.py`: 조합 요약과 선택 저장 규칙 단위 테스트.
- `tests/market_desk/test_kind_web_app.py`: API route 저장 동작 테스트.

## Testing

- 조합 요약 응답에 signature별 `sections`가 포함되는지 검증한다.
- 선택 규칙으로 `toc_1`만 저장하도록 요청하면 `toc_2` 파일이 생성되지 않는지 검증한다.
- 선택 규칙이 없는 경우 기존처럼 모든 목차가 저장되는지 기존 테스트를 유지한다.
