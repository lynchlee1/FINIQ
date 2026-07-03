# Review Findings

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
- Added `무상증자 결정` support by recognizing bonus-issue main tables and setting `증자방식=무상증자` without warning on fields that do not apply.
- Kept the existing viewer-body fetch only for wrapper HTML with missing body content; no field-value guessing fallback was added.

Verification:
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_kind_web_service.py -k "rights_issuance"` passed.
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_kind_web_service.py -k "bond_issuance or rights_issuance or parse_disclosure_html_payload_recurses_and_uses_bond_metadata_files or parse_disclosure_html_payload_warns_when_expected_form_is_missing"` passed.
- `PYTHONPATH=src python3 -m compileall -q src/finiq/market_desk/web/html_parsers/rights_issuance` passed.
- Full scan over `resources/KIND/rights_issuance/kind_html_contents_sections` checked 19,975 files and left 1 warning for a general third-party allotment disclosure whose target table is absent.
