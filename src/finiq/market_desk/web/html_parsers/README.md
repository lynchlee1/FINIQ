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
- Mode-specific parsers may use `raw_tables` and `raw_rows` internally, but saved web parse results should keep only common metadata
  (`acpt_no`, `source_file`, `mode`, `title`) plus extracted target fields.

## Web Parse Flow

The web endpoint in `disclosure_html_parse.py` follows this order:

1. Validate request options and resolve the parser from `PARSER_REGISTRY`.
2. Collect `.html` files from the input folder and load optional download manifest metadata.
3. If resume is enabled, load the existing parse JSON and skip files already present in `records` or `errors`.
4. Parse each remaining file with the selected mode parser.
5. Apply manifest metadata, collect `parse_warnings`, checkpoint periodically, and write the final JSON.

When investigating a user bug report, start with the saved JSON:

- `records`: extracted fields that downstream screens read.
- `warnings`: files that parsed but may not match the expected form.
- `errors`: files that failed and the Python exception type/message.
- `progress_log`: run order, resume behavior, checkpoints, and cancellation messages.

## Core Logic Notes

Write mode-specific extraction rules in each parser module, near the parser entrypoint.
Keep rules conservative and sample-driven: add a fixture and expected output before widening a parser to a new disclosure format.
