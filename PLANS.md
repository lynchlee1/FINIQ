# Review Findings

## 2026-07-07 Bond Issuance Manifest Title Injection

Purpose: eliminate strong `종류` missing warnings for bond issuance HTML files whose body lacks a `SECTION-1` title but whose manifest metadata has the disclosure title.

Implementation: added optional `title` injection to `parse_bond_issuance`, passed manifest titles from `html_parse_common.py` only to parsers that support a `title` parameter, updated the random-sample validation script, and documented the title source order.

Verification: added focused parser/workflow regression tests. Ran focused pytest for the new tests and representative bond parser tests.
