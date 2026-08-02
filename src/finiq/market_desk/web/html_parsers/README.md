# KIND HTML Parsing Modes

This package contains parser entrypoints for section HTML derived from downloaded KIND disclosure internal HTML.

## Modes

| Mode key | Korean name | Status |
| --- | --- | --- |
| `bond_issuance` | 사채발행파싱 | Detailed issuance, exercise, funding-purpose, and investor fields with warnings. |
| `rights_issuance` | 유무상증자파싱 | Detailed paid, bonus, mixed-issuance, and investor fields with warnings. |
| `shareholder_meeting` | 주주총회파싱 | Agenda, election, and business-purpose-change fields are implemented. |
| `asset_transaction` | 유무형자산거래파싱 | Common record and raw table structure only; no mode-specific fields. |
| `security_transaction` | 발행증권거래파싱 | Common record and raw table structure only; no mode-specific fields. |

## Shared Parsing Rules

- All modes should use the shared HTML helpers in the `common` package.
- Tables must be parsed through the span-aware grid utilities so `rowspan` and `colspan` values are expanded before field extraction.
- Mode-specific parsers return `raw_tables` for direct analysis, and the web workflow removes it before saving. `raw_rows` is not created.
- `acpt_no` and the metadata join key are the full `Path(file_path).stem`; underscores are never split and digit checks are never used as a fallback.
- Parsers and the web workflow never create `rcept_no`, `source_file`, or an empty `correction_families` field.
- Saved records keep the parser-returned `title`, `acpt_no`, conditional `doc_no` and `disclosed_at`, `상장구분`, mode-specific fields, and the direct family references `family_id`, `current_sequence`, and `family_member_count` when applicable. External title is passed only to parsers that declare a `title` argument. Full families referenced by saved records are collected once in the top-level `families` object.
- `bond_issuance` and `rights_issuance` also store `corp_name` when surrounding metadata provides the filing company name.
- `asset_transaction` and `security_transaction` currently add no mode-specific fields, field status, or parser warnings to the base record.

## Web Parse Flow

The web workflow in `features/disclosures/html_parse_common.py` follows this order:

1. Validate request options and resolve the parser from `PARSER_REGISTRY`.
2. In the canonical workspace, collect `.html` files only from `<data_root>/06-sections/<year>`, where `<year>` is a four-digit directory, and load parse metadata from `<data_root>/03-filter/<mode>/filtered.json` and `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`.
3. Parse each file with the selected mode parser.
4. Remove `raw_tables`, apply parse metadata and family references, collect `parse_warnings`, checkpoint periodically when `skip_errors=True`, and write `<data_root>/07-converted/<mode>/parsed-<mode>.json`.

The final JSON stores the source root once as top-level `input_directory`. Source files are resolved only as `input_directory/<year>/<acpt_no>.html`; records, warnings, errors, and previews do not store per-file paths or names. Warning and error items identify a file with `acpt_no`; a preview uses `acpt_no` from its outer record and does not duplicate identifiers inside `source_preview`.

When investigating a user bug report, start with the saved JSON:

- `records`: extracted fields that downstream screens read.
- `warnings`: files that parsed but may not match the expected form.
- `errors`: files that failed and the Python exception type/message.

Run order, checkpoints, and cancellation messages are emitted through progress callbacks/job status rather than saved in the parse JSON.
Warnings from successfully parsed records remain in the top-level warning report even when record filters exclude those records from `records`.

## Core Logic Notes

Write mode-specific extraction rules in each parser module, near the parser entrypoint.
For `bond_issuance` and `rights_issuance`, decide parsing behavior only from direct inspection of real files under `resources/KIND/bond_issuance` and `resources/KIND/rights_issuance`. Test fixtures and synthetic HTML verify regressions only after the behavior is fixed.

The canonical stage paths are defined in [the disclosure workspace directory contract](/docs/workspace-layout.md), and page ownership is defined in [the page directory index](/docs/disclosures/README.md). The authoritative contracts and mode-specific extraction rules are indexed in [docs/README.md](/docs/README.md).
