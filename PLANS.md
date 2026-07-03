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
