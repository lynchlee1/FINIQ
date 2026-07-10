# KIND HTML Parsing Modes

This package contains parser entrypoints for downloaded KIND disclosure viewer HTML.

## Modes

| Mode key | Korean name | Status |
| --- | --- | --- |
| `bond_issuance` | 사채발행파싱 | Architecture exists; core sample fields are implemented first. |
| `rights_issuance` | 유무상증자파싱 | Core KIND stock issue fields implemented with conservative source-based warnings. |
| `shareholder_meeting` | 주주총회파싱 | Architecture exists; detailed field rules pending. |
| `asset_transaction` | 유무형자산거래파싱 | Architecture exists; detailed field rules pending. |
| `security_transaction` | 발행증권거래파싱 | Architecture exists; detailed field rules pending. |

## Shared Parsing Rules

- All modes should use the common HTML helpers in `common.py`.
- Tables must be parsed through the span-aware grid utilities so `rowspan` and `colspan` values are expanded before field extraction.
- Mode-specific parsers return `raw_tables` for direct analysis, and the web workflow removes it before saving. `raw_rows` is not created.
- `acpt_no` and the metadata join key are the full `Path(file_path).stem`; underscores are never split and digit checks are never used as a fallback.
- Parsers and the web workflow never create `rcept_no`, `source_file`, or an empty `correction_families` field.
- Saved records keep the injected `title`, `acpt_no`, conditional `doc_no`, `상장구분`, mode-specific fields, and the direct family references `family_id`, `current_sequence`, and `family_member_count` when applicable. Full families are collected once in the top-level `families` object.
- `bond_issuance` and `rights_issuance` also store `corp_name` when surrounding metadata provides the filing company name.

## Web Parse Flow

The web endpoint in `disclosure_html_parse.py` follows this order:

1. Validate request options and resolve the parser from `PARSER_REGISTRY`.
2. Collect `.html` files from the input folder and load parse metadata from `filtered.json` and `compressed-external-html.json`.
3. Parse each file with the selected mode parser.
4. Remove `raw_tables`, apply parse metadata and family references, collect `parse_warnings`, checkpoint periodically, and write the final JSON.

The final JSON stores the source root once as top-level `input_directory`. Flat and year-split source files are resolved from that root and `acpt_no`; records, warnings, errors, and previews do not store per-file paths or names. Warning and error items identify a file with `acpt_no`; a preview uses `acpt_no` from its outer record and does not duplicate identifiers inside `source_preview`.

When investigating a user bug report, start with the saved JSON:

- `records`: extracted fields that downstream screens read.
- `warnings`: files that parsed but may not match the expected form.
- `errors`: files that failed and the Python exception type/message.

Run order, checkpoints, and cancellation messages are emitted through progress callbacks/job status rather than saved in the parse JSON.

## Core Logic Notes

Write mode-specific extraction rules in each parser module, near the parser entrypoint.
Decide parsing behavior only from direct inspection of real files under `resources/KIND/bond_issuance` and `resources/KIND/rights_issuance`. Test fixtures and synthetic HTML verify regressions only after the behavior is fixed.
