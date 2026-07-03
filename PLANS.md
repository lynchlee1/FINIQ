# Review Findings

## Listing market source-of-truth cleanup

Purpose: remove body-text listing market inference from common HTML metadata
parsing and rely on external KIND metadata for market values.

Implementation summary: removed `_listing_market()` and the full-document text
scan from `metadata.py`. `build_base_record()` now keeps the existing default
`상장시장=None` until `_apply_manifest_metadata()` overwrites the market from
download manifest, filtered metadata, or compressed external HTML metadata.
Added a regression test that body text such as `유가증권시장` is not used as a
market fallback without external metadata, and that missing external metadata
stays unknown instead of being labeled `기타`.

Verification result: `python3 -m py_compile
src/finiq/market_desk/web/html_parsers/common/metadata.py
src/finiq/market_desk/web/disclosure_html_parse.py` passed.
`PYTHONPATH=src pytest -q
tests/market_desk/test_kind_web_service.py::test_parse_disclosure_html_payload_prefers_download_manifest_market
tests/market_desk/test_kind_web_service.py::test_parse_disclosure_html_payload_does_not_infer_market_from_body
tests/market_desk/test_kind_web_service.py::test_parse_disclosure_html_payload_recurses_and_uses_bond_metadata_files
tests/market_desk/test_kind_web_service.py::test_parse_bond_issuance_extracts_kind_sample_fields`
passed.

## Bond metadata fallback simplification

Purpose: remove common metadata fallbacks that were unused by the bond issuance
HTML corpus in `resources/KIND/bond_issuance/kind_html_contents_grouped_sections`.

Implementation summary: simplified `metadata.py` so title extraction uses the
first `SECTION-1` paragraph and `<title>` fallback. Acceptance numbers come from
the filename numeric prefix, and listing market inference keeps `코스닥시장`,
`유가증권시장`, `코넥스시장`, and `기타`. Updated the legacy bond fixture so its
`SECTION-1` title structure matches the cleaned bond corpus.

Verification result: `PYTHONPATH=src python3 -m py_compile` passed for the
changed parser modules. Full parsing over 15,175 bond HTML files kept all titles
and acceptance numbers present, market counts at `기타=12,625`, `코스닥=2,368`,
`코스피=182`, and bond type counts at `CB=11,670`, `BW=3,022`, `EB=483`.
`PYTHONPATH=src pytest -q tests/market_desk/test_kind_web_service.py::test_parse_bond_issuance_extracts_kind_sample_fields`
passed.
