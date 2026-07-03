# Review Findings

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
