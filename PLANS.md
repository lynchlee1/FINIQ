## KIND External HTML Compact Document JSON Replacement

Purpose:
- Replace the current "외부 HTML JSON 압축" workflow with a smaller document-oriented JSON format for large-scale storage.
- Preserve the document selection information needed for internal HTML downloads, historical correction review, and attachment navigation without storing repeated KIND viewer shell metadata.
- Keep document option field names close to the existing extracted keys to avoid translation ambiguity: `doc_no`, `text`, `value`, `latest_flag`, and `selected`.

Assumptions:
- `records[].main_docs` and `records[].attached_docs` are excluded because they can be reconstructed from `mainDoc` and `attachedDoc` options.
- `records[].external_metadata.text_blocks` is excluded because observed values are repeated KIND UI/status notices or title/header duplicates; non-final state can be inferred from `mainDoc` latest/selected metadata.
- `records[].external_metadata.script_variables` is excluded because `_TRK_PN` equals `acpt_no` in the 50-record sample set and the other variables are static, empty, or common messages.
- Local KIND viewer samples currently cover available years 2008-2026; there are no local 2000-2007 viewer candidates in the current workspace.

Implementation plan:
- Change `compress_disclosure_external_html_payload` so it writes the compact document JSON format instead of the previous `external_metadata.selects` wrapper format.
- For each record, keep only `acpt_no`, `title`, `header`, `selected_main_doc_no`, `metadata`, `docs`, `source_sha256`, and `source_size_bytes`.
- Build `docs` from `mainDoc` and `attachedDoc` select options only.
- Exclude placeholder options with empty `doc_no`, `orgDisclsId`, select attrs, option attrs, scripts, forms, resources, links, frames, and text blocks.
- Each `docs[]` item includes `select_id`, `select_name`, `option_index`, `doc_no`, `text`, `value`, `latest_flag`, and `selected`.
- Keep the existing API action key and output filename for compatibility, but update the format identifier to a new version.
- Update internal content download target collection to read `docs[]`, while retaining compatibility with legacy `selected_main_doc_no`/`main_docs` payloads where simple.
- Update the web page label/help text so the existing "외부 HTML JSON 압축" action describes the compact document JSON output.

Verification plan:
- Add backend tests proving the compressed JSON omits discarded fields and preserves all main/attached document options with original key names.
- Add a content-target test proving internal HTML download target collection works from the new compact JSON.
- Update existing tests that asserted old `external_metadata` fields.
- Run relevant pytest coverage for KIND JSON parsing, external compression, content target collection, and shareholder fixture behavior.

Implementation summary:
- `compress_disclosure_external_html_payload` now writes `finiq_disclosure_external_html_docs_v1` records with `docs[]` instead of the old `external_metadata` wrapper.
- `docs[]` contains only `mainDoc` and `attachedDoc` non-placeholder options and preserves original option key names: `doc_no`, `text`, `value`, `latest_flag`, and `selected`.
- Internal content HTML target collection now reads selected `mainDoc` entries from `docs[]`, with fallback compatibility for legacy `selected_main_doc_no`/`main_docs` payloads.
- The MarketDesk HTML download page now labels the action as "외부 HTML 문서 JSON 압축" and describes the compact document JSON output.
- Corrected internal content target precedence so selected compact `docs[]` `mainDoc` entries win over stale legacy `selected_main_doc_no`, then falls back to legacy values and first available document options.

Verification:
- `python3 -m pytest tests/market_desk/test_kind_web_service.py -k "download_disclosure_html_contents_payload or compressed_external_json or compact_docs_json or compress_disclosure_external_html_payload"` passed: 10 passed, 130 deselected.
- `python3 -m pytest tests/data_scraper/test_kind_json_conversion.py tests/data_scraper/test_shareholder_meeting.py` passed: 218 passed.
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build` passed.
- Temp sample compression against `samples/kind_html` with `limit=3` produced `finiq_disclosure_external_html_docs_v1`; records contain only `acpt_no`, `title`, `header`, `selected_main_doc_no`, `metadata`, `docs`, `source_sha256`, and `source_size_bytes`, with no `external_metadata`.
