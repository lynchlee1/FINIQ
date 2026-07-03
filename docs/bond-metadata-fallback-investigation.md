# Bond HTML Metadata Fallback Investigation

Scope: `resources/KIND/bond_issuance/kind_html_contents_grouped_sections`

This note investigates the fallback logic in
`src/finiq/market_desk/web/html_parsers/common/metadata.py` against the bond
issuance HTML corpus and proposes a smaller system that preserves current
outputs for that corpus.

## Corpus

- HTML files: 15,175
- Metadata sidecars found under the corpus: none
  - no `kind_disclosure_html_manifest.json`
  - no `filtered.json`
  - no `compressed-external-html.json`

Because there are no sidecars in this directory, the current bond parser depends
on the HTML/file-path metadata fallback behavior directly.

## Current Fallback Usage

### Metadata Logic Inventory

For bond issuance parsing, the direct path is:

`parse_bond_issuance()` -> `_build_bond_parse_context()` -> `build_base_record()`

The bond parser does not call `fetch_selected_viewer_body()` and does not call
`preserve_viewer_metadata()`. Those body/viewer preservation fallbacks are used
by other paths, especially rights issuance parsing and source preview, so this
corpus cannot prove whether they are removable globally.

Within `metadata.py`, the bond path exercises:

- `extract_title(document)`
- `_viewer_acpt_no(document, file_path)`
- `extract_acpt_no(file_path)` through `_viewer_acpt_no()`
- `_listing_market(document_text)`
- fixed `rcept_no=None`
- fixed `correction_families={}`

`rcept_no` has no HTML fallback in `build_base_record()` for this corpus. If a
later workflow has external sidecar metadata, `disclosure_html_parse` may fill
`rcept_no` after parser output, but no such sidecars exist under the scoped bond
directory.

### Title

Current `extract_title()` tries these sources in order:

1. `meta[property=og:title]`
2. `meta[name=title]`
3. `<title>`
4. `p.SECTION-1` containing `사채`
5. any `p.SECTION-1`
6. text node under any `p.SECTION-1`
7. any `title` attribute
8. `h1`
9. `h2`

Observed selected source:

| selected source | count |
| --- | ---: |
| `p.SECTION-1` containing `사채` | 14,771 |
| `<title>` | 404 |

Observed non-empty source availability:

| source | count |
| --- | ---: |
| `p.SECTION-1` containing `사채` | 14,771 |
| any `p.SECTION-1` | 14,771 |
| `p.SECTION-1/text()` | 14,429 |
| `<title>` | 404 |

The other title fallbacks were never non-empty in this corpus.

Important detail: there were no files where both `<title>` and `p.SECTION-1`
were usable. Therefore this smaller title order gives identical title strings
for the corpus:

1. `p.SECTION-1` containing `사채`
2. `<title>`

Using only `p.SECTION-1` is not equivalent: 404 legacy files would lose their
title. Those legacy titles look like `:: 71105_전환사채 발행결정` and still drive
the bond `종류` classification correctly.

### Acceptance Number

Current `_viewer_acpt_no()` tries:

1. `//input[@name='acptNo']/@value`
2. filename stem via `extract_acpt_no(file_path)`

Observed result:

| source | count |
| --- | ---: |
| `acptNo` input present | 0 |
| filename fallback used | 15,175 |

For this corpus, the HTML input lookup is unnecessary and the filename is the
actual source of truth. Removing the filename fallback would make all `acpt_no`
values empty.

### Listing Market

Current `_listing_market()` scans all document text in this priority order:

1. `코스닥시장` -> `코스닥`
2. `유가증권시장` -> `코스피`
3. `코넥스시장` -> `코넥스`
4. otherwise `기타`

Observed result:

| result | count |
| --- | ---: |
| `기타` | 12,625 |
| `코스닥` | 2,368 |
| `코스피` | 182 |
| `코넥스` | 0 |

Phrase combinations:

| phrases present | count |
| --- | ---: |
| none | 12,625 |
| `코스닥시장` only | 2,244 |
| `유가증권시장` only | 182 |
| both `코스닥시장` and `유가증권시장` | 124 |

The priority order matters for 124 files where both phrases appear; preserving
current output requires `코스닥시장` to remain before `유가증권시장`. The `코넥스시장`
branch is unused for this corpus.

## Current Parse Output Baseline

Running the current bond parser over all files produced:

| field/result | count |
| --- | ---: |
| records | 15,175 |
| title present | 15,175 |
| acpt_no present | 15,175 |
| `상장구분=기타` | 12,625 |
| `상장구분=코스닥` | 2,368 |
| `상장구분=코스피` | 182 |
| `종류=CB` | 11,670 |
| `종류=BW` | 3,022 |
| `종류=EB` | 483 |

There were no missing `종류` warnings, so the existing title sources are
sufficient for current bond type classification.

## Implemented Less-Fallback System

For this bond corpus, the equivalent minimal behavior has been implemented in
`metadata.py`:

```python
def extract_bond_title(document):
    return first_non_empty(
        section1_paragraph_containing("사채"),
        title_tag_text(),
    )

def extract_bond_acpt_no(file_path):
    return numeric_prefix_from_filename(file_path)

def extract_bond_listing_market(document_text):
    if "코스닥시장" in document_text:
        return "코스닥"
    if "유가증권시장" in document_text:
        return "코스피"
    return "기타"
```

This removes title sources that are unused in the corpus:

- `meta[property=og:title]`
- `meta[name=title]`
- generic `p.SECTION-1`
- `p.SECTION-1/text()`
- arbitrary `title` attributes
- `h1`
- `h2`

It also removes the unused `acptNo` HTML input lookup. The `코넥스시장` market
branch is retained even though it is unused in this specific corpus.

## Implementation Note

The common `metadata.py` implementation now follows the bond-corpus evidence
directly. This intentionally removes broad fallback behavior that was not used
by the scoped bond corpus.

If other parser modes are completed later, they should be validated against
their own corpora before adding fallback behavior back.

The retained behavior is:

- title: `SECTION-1 + 사채`, then `<title>`
- acpt_no: filename numeric prefix
- market: `코스닥시장`, `유가증권시장`, `코넥스시장`, else `기타`

## Verification Commands

The investigation used read-only commands with `PYTHONPATH=src python3`.

Checks performed:

- counted selected `extract_title()` source per HTML file
- counted non-empty availability of every current title fallback source
- compared current title output with the smaller title policy
- counted `acptNo` input availability versus filename fallback
- counted listing market phrase combinations
- parsed all bond files with the current parser and counted output field
  presence/classification
