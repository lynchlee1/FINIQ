# Review Findings

## Rights Issuance Title-Based Classification

Purpose: Classify rights issuance type from the disclosure title only, without falling back to table structure signatures.

Implementation summary:
- Replaced `_main_rights_rows()` table-signature detection with title-only issuance type detection: `paid`, `bonus`, `mixed`, or `unknown`.
- Stored the title-derived issuance type in the rights parse context and made bonus-specific extraction behavior depend on that value.
- Added regression coverage showing bonus-looking table rows no longer cause a bonus classification when the title is missing.

Verification:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "rights_issuance"` passed.
- `PYTHONPATH=src .venv/bin/python -m compileall -q src/finiq/market_desk/web/html_parsers/rights_issuance` passed.
- Full title scan over `resources/KIND/rights_issuance/kind_html_contents_sections` classified all 19,975 files from title alone: 18,393 `paid`, 1,071 `bonus`, 511 `mixed`, 0 `unknown`.

## Bond Issuance Maturity and Issue Method Parsing

Purpose: Fix `20111206000056` bond issuance parsing so legacy `사채만기` rows produce `만기일`, and add `사채발행방법` extraction to the parsed bond issuance output.

Implementation summary:
- Added legacy `사채만기` fallback after the existing `사채만기일` lookup.
- Added `사채발행방법` to the bond parser schema, parse payload field lists, summary detail view, and random-sample validation script.
- Kept missing-investor warnings even when `투자자=[]`, so humans can review disclosures whose target table is absent.
- Added regression coverage for parsed payloads, summary fields, current KIND fixtures, and the `20111206000056` legacy row shape.

Verification:
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_kind_web_service.py -k "bond_issuance or bond_parse_summary or parse_disclosure_html_payload_recurses_and_uses_bond_metadata_files or parse_disclosure_html_payload_warns_when_expected_form_is_missing"` passed.
- `PYTHONPATH=src python3 - <<'PY' ... parse_bond_issuance(resources/KIND/bond_issuance/kind_html_contents_grouped_sections/2011/20111206000056.html) ... PY` returned `만기일=2011년 12월 14일`, `사채발행방법=공모`, `투자자=[]`, with a missing-investor warning for human review.
- `npx tsc -p finiq_GUI/apps/market-desk/tsconfig.json --noEmit` passed.

## Rights Issuance Source-Based Parsing

Purpose: Implement `유무상증자파싱` using the same conservative, source-based parsing style as `사채발행파싱`, while keeping fallback logic minimal.

Implementation summary:
- Added a rights issuance parse context and row wrapper so extraction uses normalized non-correction table rows consistently.
- Added explicit extraction rules and `parse_warnings` for missing required sources instead of silently returning empty values.
- Fixed legacy stock labels such as `보통주`/`우선주` and scheduled issue-price rows so older KIND forms parse stock counts and issue prices correctly.
- Added `무상증자 결정` support and later moved the paid/bonus/mixed distinction to title-only classification.
- Removed the viewer-body fetch fallback because the cleaned `resources/KIND/rights_issuance/kind_html_contents_sections` inputs already contain parseable body tables.
- Simplified date row lookups to the common whitespace-insensitive row search instead of exact-label fallback helpers.

Verification:
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_kind_web_service.py -k "rights_issuance"` passed.
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_kind_web_service.py -k "bond_issuance or rights_issuance or parse_disclosure_html_payload_recurses_and_uses_bond_metadata_files or parse_disclosure_html_payload_warns_when_expected_form_is_missing"` passed.
- `PYTHONPATH=src python3 -m compileall -q src/finiq/market_desk/web/html_parsers/rights_issuance` passed.
- Full scan over `resources/KIND/rights_issuance/kind_html_contents_sections` checked 19,975 files and left 1 warning for a general third-party allotment disclosure whose target table is absent.
