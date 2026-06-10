## KIND External HTML Variable Metadata Classification

Purpose:
- Reduce storage pressure from KIND viewer wrapper HTML under `kind_html` without modifying original files.
- Extract all compact metadata first, then classify each extracted field into efficient per-disclosure storage candidates.
- Prefer fields that vary by disclosure. Repeated static viewer UI, item descriptions, generic labels, common scripts, and common resources should be treated as discard candidates unless later analysis proves they are needed.

Implementation summary:
- Extended `compress_disclosure_external_html_payload` to use a compact external HTML extractor.
- Kept existing compressed record fields (`acpt_no`, `title`, `selected_main_doc_no`, `main_docs`, `attached_docs`, manifest `metadata`) for compatibility.
- Added `external_metadata` with meta tags, forms, all inputs, all selects/options, links, frames, external resources, scripts, direct text blocks, simple inline script variables, source SHA-256, and source byte size.
- Current tests intentionally keep every extracted part in the JSON output so no potentially useful metadata is lost during validation.
- Added `uncommitted_feature_extraction_table.json` at the project root to classify extracted fields as `save` or `discard`.
- Added `scripts/build_kind_external_metadata_examples_xlsx.py` to run real KIND viewer HTML examples and create a review workbook.
- Generated `scripts/kind_external_metadata_examples.xlsx` from 10 sample files with Summary, Save Examples, Discard Examples, and Field Counts sheets.
- The current storage recommendation is:
  - `save`: disclosure-specific identifiers, selected document values, richer raw select metadata, attached document lists, source row metadata, disclosure-specific notices, script variables that contain disclosure identifiers/state, and source integrity/size checks.
  - `discard`: `main_docs` when `external_metadata.selects` is retained, duplicated all-input values, static KIND viewer/UI metadata, generic meta tags, common forms/buttons/labels, repeated resource/script references, generic links/icons, and repeated frame shell attributes.
- Updated `scripts/build_kind_external_metadata_examples_xlsx.py` so Save/Discard example cells keep full JSON/text values instead of 500-character previews.

Verification:
- `/Library/Frameworks/Python.framework/Versions/3.13/bin/pytest tests/market_desk/test_kind_web_service.py -k compress_disclosure_external_html_payload`
- `/Library/Frameworks/Python.framework/Versions/3.13/bin/pytest tests/data_scraper/test_kind_json_conversion.py tests/market_desk/test_kind_web_service.py`
- `python3 -m pytest tests/market_desk/test_kind_web_service.py -k compress_disclosure_external_html_payload` passed: 2 passed, 137 deselected.
- `python3 -m pytest tests/data_scraper/test_kind_json_conversion.py tests/market_desk/test_kind_web_service.py` passed: 152 passed.
- Generated sample compressed JSON from `samples/kind_html` into `generated_external_metadata_json/compressed-external-html.json`: 10 found, 10 compressed, verification passed with 0 missing records.
- `python3 -m json.tool generated_external_metadata_json/compressed-external-html.json`
- `python3 scripts/build_kind_external_metadata_examples_xlsx.py` generated `scripts/kind_external_metadata_examples.xlsx`: 10 records, verification passed with 0 missing records.
- XLSX package check passed after full-value export update: required workbook parts present; sheets `Summary`, `Save Examples`, `Discard Examples`, `Field Counts`; row counts `[11, 121, 111, 101]`; no generated truncation ellipsis found.
- `PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 - <<'PY' ...` checked 480 real KIND viewer HTML samples across `bond_issuance`, `rights_issuance`, and `shareholder_meeting`; no missing values found for the extracted attribute/text/link/resource/frame/script field set.
- `PYTHONPATH=src python3 - <<'PY' ...` sample conversion against one `bond_issuance`, one split `rights_issuance`, and one split `shareholder_meeting` `kind_html` file; all verification checks passed.
- `python3 -m json.tool uncommitted_feature_extraction_table.json`
