# Review Findings

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
