# KIND HTML Parsing Modes

This package contains parser entrypoints for downloaded KIND disclosure viewer HTML.

## Modes

| Mode key | Korean name | Status |
| --- | --- | --- |
| `bond_issuance` | 사채발행파싱 | Architecture exists; core sample fields are implemented first. |
| `rights_issuance` | 유무상증자파싱 | Architecture exists; detailed field rules pending. |
| `shareholder_meeting` | 주주총회파싱 | Architecture exists; detailed field rules pending. |
| `asset_transaction` | 유무형자산거래파싱 | Architecture exists; detailed field rules pending. |
| `security_transaction` | 발행증권거래파싱 | Architecture exists; detailed field rules pending. |

## Shared Parsing Rules

- All modes should use the common HTML helpers in `common.py`.
- Tables must be parsed through the span-aware grid utilities so `rowspan` and `colspan` values are expanded before field extraction.
- Mode-specific parsers should extract fields from logical rows and keep the common metadata fields:
  `acpt_no`, `source_file`, `mode`, `title`, `raw_tables`, and `raw_rows`.

## Core Logic Notes

Write mode-specific extraction rules in each parser module, near the parser entrypoint.
Keep rules conservative and sample-driven: add a fixture and expected output before widening a parser to a new disclosure format.
