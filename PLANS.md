# Review Findings

## Completed: HTML Section Save Original Folder Structure

Purpose:
- `공시원문 목차 분리` 저장 결과가 `toc_1`, `toc_2` 폴더를 만들지 않고 원본 데이터의 연도 폴더 구조를 보존하게 했다.

Implementation summary:
- 목차 HTML 저장 경로를 `결과 데이터 경로/toc_id/원본상대경로`에서 `결과 데이터 경로/원본상대경로`로 변경했다.
- 서비스 테스트와 API 작업 테스트가 `2008/20260422000832.html` 구조 및 `toc_1` 폴더, `_1`/`_2` suffix 파일 미생성을 검증하게 했다.

Verification:
- `pytest tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_writes_every_toc tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_continues_after_files_without_toc tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_saves_all_toc_sections tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_applies_pattern_toc_selection -q` passed: 5 tests.
- `pytest tests/market_desk/test_kind_web_service.py tests/market_desk/test_kind_web_app.py -q` passed: 190 tests.

## Completed: HTML Section Pattern Save Rules

Purpose:
- `공시원문 목차 분리`에서 모든 HTML을 저장 대상으로 유지하면서, 목차 조합별로 저장할 `toc_*` 항목을 선택할 수 있게 했다.

Implementation summary:
- 목차 조합 요약 응답에 조합별 `sections` 목록을 추가했다.
- `section_save_rules` payload를 저장 작업에 추가해 signature별 선택된 `toc_id`만 저장하도록 했다.
- `목차 조합 모아보기`에 조합별 저장 대상 목차 체크박스를 추가하고, 선택 상태를 저장 실행 payload로 전달했다.
- `작업 실행`에서는 표시용 `최대 표시 파일 수`를 전달하지 않도록 해 전체 HTML을 저장 대상으로 유지했다.
- 저장 완료 후 저장 대상 파일 수와 실제 저장 파일 수를 비교하는 무결성 검사 summary와 로그를 추가했다.

Verification:
- `pytest tests/market_desk/test_kind_web_service.py::test_summarize_disclosure_html_section_kinds_payload_counts_unique_toc_sequences tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui tests/market_desk/test_kind_web_app.py::test_html_section_kinds_route_returns_unique_toc_sequence_counts tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_saves_all_toc_sections tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_applies_pattern_toc_selection -q` passed: 6 tests.
- `npm run build -w @finiq/app-market-desk` passed.

The review is complete. Topics without review findings were removed. Remaining topics below need fixes before they can be considered free of errors.

## Disclosure Section Split Parallel Loading

Review finding:
- `src/finiq/market_desk/web/disclosure_html_sections.py`: `_map_html_files()` materializes every worker result before `inspect_disclosure_html_sections_payload()` or `save_disclosure_html_sections_payload()` checks `cancel_check`, so cancelling a large inspect/save job does not stop reads or writes until the whole worker pool finishes. Stream futures or pass cancellation into the worker loop so cancellation can interrupt long folder jobs promptly.

## Disclosure HTML Section Folder Review

Review findings:
- `frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx`: The page still exposes `결과 데이터 경로`, `startSave()`, `/api/disclosures/html/sections/save/start`, and the `실행` button even though the folder-review topic says the screen removed the visible output directory and bulk save action.
- `tests/market_desk/test_kind_web_service.py`: UI terminology coverage still asserts `/api/disclosures/html/sections/save/start`, `startSave`, `Play`, and `폴더 요약` absence, so the tests enforce the older bulk-processing UI instead of the folder-review behavior.

## Disclosure Section Kinds API Mismatch

Review findings:
- `tests/market_desk/test_kind_web_service.py`: The module imports and tests `summarize_disclosure_html_section_kinds_payload`, but `src/finiq/market_desk/web/disclosure_html_sections.py` no longer defines that function. The service test module fails during collection with `ImportError`, so the suite cannot reach the individual assertions.
- `tests/market_desk/test_kind_web_app.py`: The app tests still expect `/api/disclosures/html/sections/kinds`, while `src/finiq/market_desk/web/routers/workflows.py` no longer registers that route. Either restore the function/route or remove the stale tests and UI expectations as part of the folder-review cleanup.
- `frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx`: The current implementation uses `reviewPanelRef`, `scrollToReviewPanel`, and `activeReviewView`, but the terminology test still asserts removed names such as `sectionPanelRef`, `scrollToSectionPanel`, and `activePanel`. Those assertions need to be updated to the current one-panel review behavior.
