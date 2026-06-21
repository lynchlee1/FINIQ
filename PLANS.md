# Completed Changes

## Disclosure Review Button Pattern Correction

Purpose:
- Align the section review buttons with the existing `공시원문 내부 저장` data-path mode-button pattern.

Implementation summary:
- Renamed the row action from `목차별 보기` to `원문 보기` and removed the redundant `공시 열기` row action.
- Changed review-panel actions to the existing inline segmented button style using `default`/`ghost` variants.
- Rendered the same `공시 원문` / `목차별 보기` navigation actions on both review panels.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` failed before implementation because `원문 보기` and the segmented button pattern were missing.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` passed after implementation.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.
- `npm run build -w @finiq/app-market-desk` passed.

## Disclosure Review Panel Navigation

Purpose:
- Replace the no-longer-needed `목차 분리` action in the source review panel with view navigation buttons.

Implementation summary:
- Removed the selected-source `목차 분리` action prop and handler.
- Added `공시 원문` and `목차별 보기` buttons in the `공시 원문` card action area.
- Added a section panel ref so the new `목차별 보기` button scrolls to the section review panel.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` failed before implementation because section-panel navigation was missing.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` passed after implementation.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.
- `npm run build -w @finiq/app-market-desk` passed.

## Disclosure Row Vertical Alignment

Purpose:
- Vertically center elements in `개별 공시` rows.

Implementation summary:
- Changed disclosure row data cells from top alignment to middle alignment.
- Centered row action buttons along the row height while preserving existing horizontal behavior.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` failed before implementation because `align-middle` was missing.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` passed after implementation.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.
- `npm run build -w @finiq/app-market-desk` passed.

## Disclosure Stable Review Panels

Purpose:
- Show section counts in `개별 공시` and keep `공시 원문` / `목차별 보기` panels visible before a disclosure is selected.

Implementation summary:
- Added `section_count` to the paged source-list API by inspecting only the currently returned page of files.
- Added a `목차 수` column to the `개별 공시` table.
- Changed `공시 원문` and `목차별 보기` cards to always render with empty-state messages until a source or split result is available.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_list_disclosure_html_section_sources_payload_pages_with_current_page_toc_counts tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` failed before implementation because `section_count` and `목차 수` were missing.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_list_disclosure_html_section_sources_payload_pages_with_current_page_toc_counts tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` passed after implementation.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.
- `npm run build -w @finiq/app-market-desk` passed.
- Restarted the local API server on `127.0.0.1:8765` and confirmed `/api/disclosures/html/sections/list` returns `section_count` for first-page files.

## Disclosure XForms Wrapper Preservation

Purpose:
- Fix section review rendering for XForms disclosures such as `2008/20080825000156.html`.

Implementation summary:
- Preserved the original `class="xforms"` ancestor wrapper when splitting XForms fallback sections.
- Kept the existing section boundaries so `정정신고(보고)` and the main `주주총회소집 결의` body remain separate.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_split_content_html_sections_uses_xforms_title_fallback` failed before implementation because split section HTML dropped `class="xforms"`.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_split_content_html_sections_uses_xforms_title_fallback` passed after preserving the wrapper.
- Directly inspected `resources/KIND/shareholder_meeting/kind_html_contents/2008/20080825000156.html`; it returns 2 sections, both with `class="xforms"`, and the main section does not contain `정정신고(보고)`.
- Restarted the local API server on `127.0.0.1:8765` and confirmed the split API returns 2 sections with `class="xforms"` for `2008/20080825000156.html`.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.

## Disclosure Source Load Button Placement

Purpose:
- Move `소스 불러오기` into the `개별 공시` card header so source loading starts from the disclosure list area.

Implementation summary:
- Added the source-load action to the `개별 공시` card actions alongside pagination.
- Removed the duplicate source-load button from the lower `작업 실행` card.
- Kept the existing loading/disabled behavior while moving the UI control.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` failed before implementation because `FolderOpen` still lived in the page file.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` passed after moving the button.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.
- `npm run build -w @finiq/app-market-desk` passed.

## Disclosure Section Row Review Actions

Purpose:
- Fix `개별 공시` row review controls so a user can open a disclosure and directly view it split by TOC section.

Implementation summary:
- Removed the redundant per-page maximum display sentence from the `개별 공시` card.
- Changed `공시 열기` to a normal button that scrolls to the loaded source panel.
- Added `목차별 보기` as a row action and result card title for splitting the selected disclosure immediately.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.
- `npm run build -w @finiq/app-market-desk` passed.
- `curl` through `http://127.0.0.1:3000/api/disclosures/html/sections/list` returned 20 first-page files.
- `curl` through `http://127.0.0.1:3000/api/disclosures/html/sections/source/split` returned `정정신고(보고)` and `주주총회소집 결의` as separate sections for `2008/20081014000388.html`.

## Disclosure Section Lazy Review

Purpose:
- Load `개별 공시` in pages of 20 by default and split only the selected disclosure for review.

Implementation summary:
- Added a page-based source list API that returns file metadata without scanning every HTML file's TOC.
- Added a selected-source split API that returns section HTML for one disclosure.
- Updated `공시원문 목차 분리` to show previous/next page controls, load the selected source in an iframe, and show split TOC HTML after `목차 분리`.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'html_section or xforms_title_fallback or ui_terminology'` passed.
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'html_section'` passed.
- `npm run build -w @finiq/app-market-desk` passed.

## Disclosure XForms Correction TOC Split

Purpose:
- Separate leading XForms correction disclosures such as `정정신고(보고)` from the main disclosure body in `공시원문 목차 분리`.

Implementation summary:
- Added XForms fallback detection for meaningful pre-`xforms_title` blocks whose first text starts with `정정신고`.
- Updated the XForms section split test to expect `정정신고(보고)` as `toc_1` and the main body as `toc_2`.

Verification:
- `/tmp/finiq-debug-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'xforms_title_fallback or split_content_html_sections_uses_toc_boundaries or legacy_section_one'` passed.
- Directly inspected `resources/KIND/shareholder_meeting/kind_html_contents/2008/20081014000388.html`; it now reports `toc_1 정정신고(보고)` and `toc_2 주주총회소집 결의`.

The review is complete. Topics without review findings were removed. Remaining topics below need fixes before they can be considered free of errors.

## Disclosure Section Split Parallel Loading

Review finding:
- `src/finiq/market_desk/web/disclosure_html_sections.py`: `_map_html_files()` materializes every worker result before `inspect_disclosure_html_sections_payload()` or `save_disclosure_html_sections_payload()` checks `cancel_check`, so cancelling a large inspect/save job does not stop reads or writes until the whole worker pool finishes. Stream futures or pass cancellation into the worker loop so cancellation can interrupt long folder jobs promptly.

## Disclosure HTML Section Folder Review

Review findings:
- `frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx`: The page still exposes `결과 데이터 경로`, `startSave()`, `/api/disclosures/html/sections/save/start`, and the `실행` button even though the folder-review topic says the screen removed the visible output directory and bulk save action.
- `tests/market_desk/test_kind_web_service.py`: UI terminology coverage still asserts `/api/disclosures/html/sections/save/start`, `startSave`, `Play`, and `폴더 요약` absence, so the tests enforce the older bulk-processing UI instead of the folder-review behavior.
