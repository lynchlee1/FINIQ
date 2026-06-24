# Review Findings

## Completed: HTML Section Split Cancellation

Purpose:
- `공시원문 목차 분리` inspect/save jobs should stop promptly when cancellation is requested instead of materializing every worker result first.

Implementation summary:
- `_map_html_files()` now streams worker results and checks `cancel_check` before each sequential file, before submitting more parallel work, and after completed futures.
- `inspect_disclosure_html_sections_payload()` and `save_disclosure_html_sections_payload()` consume streamed results and return `{"cancelled": True}` without processing later files after cancellation.
- Added regression coverage proving inspect/save jobs do not continue into the next file after cancellation.

Verification:
- `pytest tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_writes_every_toc tests/market_desk/test_kind_web_service.py::test_inspect_disclosure_html_sections_payload_stops_before_next_file_when_cancelled tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_preserves_multiple_selected_sections tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_stops_before_next_file_when_cancelled -q` failed before implementation: save summaries/content and save cancellation still showed the bug.
- `pytest tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_writes_every_toc tests/market_desk/test_kind_web_service.py::test_inspect_disclosure_html_sections_payload_stops_before_next_file_when_cancelled tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_preserves_multiple_selected_sections tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_stops_before_next_file_when_cancelled -q` passed: 4 tests.
- `node --test --test-name-pattern "html section split can cancel save jobs and source loading|html section split persists data path fields" tests/frontend/pathLayout.test.mjs` passed: 2 tests.
- `../../../node_modules/.bin/tsc --noEmit -p tsconfig.json` passed.

## Completed: HTML Section Save Original Folder Structure

Purpose:
- Preserve the current original-folder output layout without losing earlier selected sections when a disclosure has multiple selected `toc_*` entries.

Implementation summary:
- `save_disclosure_html_sections_payload()` now writes one output file per source disclosure containing all selected section HTML fragments, instead of overwriting the same path once per selected section.
- Save summaries now count output files (`saved_files`/`expected_files`) so the integrity check matches actual filesystem paths.
- Service and route tests now assert saved file contents, including filtered pattern rules, so overwritten section content is covered.

Verification:
- `pytest tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_writes_every_toc tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_continues_after_files_without_toc tests/market_desk/test_kind_web_service.py::test_inspect_disclosure_html_sections_payload_stops_before_next_file_when_cancelled tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_preserves_multiple_selected_sections tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_stops_before_next_file_when_cancelled tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_saves_all_toc_sections tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_applies_pattern_toc_selection -q` passed: 8 tests.
- `pytest tests/test_persistence_api.py::test_html_section_split_output_directory_persists -q` passed: 1 test.

## Reviewed: Disclosure HTML Section Folder Review

Decision:
- Intentional current behavior. The page exposes `결과 데이터 경로`, the bulk save route, and the `실행` action by design in the current implementation, and `docs/ui-terminology.md` includes the `결과 데이터 경로` term for output path inputs.
- The current frontend persistence tests also assert `html_section_split_output_directory`, save cancellation, and the save route. Removing these controls would conflict with the active save workflow fixed above.

Verification:
- No UI code change was made for this item.
