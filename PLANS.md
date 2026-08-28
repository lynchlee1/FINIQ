# Completed Changes Requiring Follow-up

## 2026-08-28: hide derived filters from HTML storage workflows

- Purpose: keep subfilters out of `공시원문 외부 저장`, `공시원문 내부 저장`, and `공시원문 목차 분리`, where outputs belong to the top-level filter rather than a derived filter.
- Implementation: filter preset responses to top-level entries in the shared external/internal HTML page and the section-split page. Keep derived-filter selection available in `공시원문 변환`.
- Verification: the focused derived-filter regression tests passed, as did the Market Desk TypeScript check and all 200 frontend tests.

## 2026-08-28: expose missing right-dock progress intervals

- Purpose: restore the missing `진행 확인 간격 (건)` control in right-side settings panels that run multiple disclosure stages, external HTML compression, or section inspection and saving.
- Implementation: add the shared progress-interval field to `공시 자동화`, the external HTML compression mode, and `공시원문 목차 분리`; persist it in the automation profile, pass it through stages 03~07, and use it for compression, section inspection, and section save log cadence. Remove the unrelated count-suffix edits made during the initial misdiagnosis.
- Verification: 441 related backend tests passed with 166 skips, all 199 frontend tests passed, and the Market Desk TypeScript and whitespace checks passed. Browser verification confirmed the field in the automation, external HTML compression, and section-split right-side settings panels with no console errors.

## 2026-08-28: accept legacy KIND fragments in section inspection

- Purpose: remove the false `HTML head is required` failure for historical KIND responses that are valid body fragments, while keeping genuinely unsupported TOC structures visible and separating canonical `KIND 원본 없음` placeholders from damaged files.
- Implementation: the section parser now documents every input through one fragment-capable HTML parser and recognizes legacy lowercase `section-N` classes. Full inspection continues after individual failures, reports bounded file paths with Korean causes, and separately counts source-unavailable placeholders. The page shows the total by category and the first concrete problem; source lists mark `KIND 원본 없음` and disable only their TOC action.
- Verification: all 207,313 current stage-05 files passed the full inspection: bond issuance 24,710 normal plus one source-unavailable placeholder, rights issuance 39,621 normal plus one placeholder, and shareholder meetings 142,980 normal. The broader suite passed 564 Python tests with 166 skips and all 199 frontend tests; Market Desk TypeScript compilation, Python compilation, and whitespace checks also passed.

## 2026-08-28: isolate disclosure stage-link validation

- Purpose: prevent a broken storage link in an unrelated disclosure stage from blocking work that never reads or writes that stage.
- Implementation: disclosure workspace stage paths now resolve and create on access. Section inspection resolves only stage 05, section saving resolves stages 05 and 06, and internal HTML download resolves stages 04-compress and 05. Required broken links still fail without falling back to local data, while the stage-link status API continues to report every broken link.
- Verification: all 190 workspace, compression, web-app, and automation tests passed. Regression cases cover broken unrelated 01/04-download links, required 05/06 failures, and the 04-compress/05 internal-download boundary. The repository's current `database` workspace resolved section and internal-download paths successfully despite its stale `/Volumes/Untitled/finiq-db` links; Python compilation and whitespace checks also passed.

## 2026-08-28: restrict correction removal to the leading section

- Purpose: encode the verified invariant that a correction disclosure's correction block is always the first structurally split section, so later business headings containing `정정` can never be removed.
- Implementation: correction filtering and pre-save validation now inspect only the first section. They remove it when its whitespace-normalized title contains the single token `정정`; all later sections are preserved without correction-title inspection.
- Verification: regression coverage confirms that the leading correction preamble is removed and that a later heading containing `정정` remains. All 32 focused splitter/save tests and 132 web-app/automation tests passed; Python compilation and whitespace checks also passed.

## 2026-08-28: preserve and classify hierarchical KIND TOCs

- Purpose: replace the flat `SECTION-N` splitter with a structural TOC classifier that preserves source IDs and hierarchy, while no longer describing XForms document titles as TOC entries.
- Implementation: source `toc_N` headings now keep their IDs and classify `COVER-TITLE`, `PART`, and `SECTION-N` as cover, part, and numbered section levels. Each section exposes its kind, level, nearest structural parent, and whether it is a real TOC entry. Preamble and XForms single-form bodies are explicitly non-TOC; correction filtering still runs only after all ranges are split. The preview UI indents entries by structural level.
- Verification: KIND receipt `20260827000625` produced one correction preamble plus all 67 source TOCs: one cover, four parts, nineteen level-1 sections, and forty-three level-2 sections. After correction removal, `toc_1` through `toc_67` remained. A fixed-seed random sample of 20 current stage-05 files passed, as did 27 focused splitter tests, 132 web-app/automation tests, 199 frontend tests, and the Market Desk TypeScript check. Full-corpus verification was intentionally not used for acceptance.

## 2026-08-28: reuse stable KIND download inspection results

- Purpose: remove the second full HTML parse performed during KIND count comparison without weakening page completeness or local file integrity checks.
- Implementation: carry each folder's validated page totals and a compact fingerprint of result filenames, sizes, and modification times into KIND comparison; reuse the result when the folder and page size are unchanged, and run the existing complete inspection only for a changed folder.
- Verification: 383 download service tests and 80 related downloader/automation tests passed. On the available 28,147-byte real KIND result page repeated 500 times, the second-phase work fell from 1.629 seconds of parsing to 0.021 seconds of file-state checks (98.7% reduction for that phase); the original 37-range dataset was not present locally for a full end-to-end benchmark.

## 2026-08-28: standard external HTML compression output

- Purpose: make the compression stage follow the standard workspace contract even when callers omit explicit input and output paths.
- Implementation: resolve both paths from `data_root` and `mode`, create the canonical `04-external-html-compress/<mode>` directory when saving, and retain the error that prevents falling back to the input HTML directory when no workspace is supplied.
- Verification: the workspace/compression regression set passed 55 tests, and the broader compression, disclosure automation, and pipeline resilience set passed 87 tests.

## 2026-08-14: shareholder-meeting entity and relationship extraction

- Purpose: turn shareholder-meeting notices and results into evidence-backed people, organizations, agendas, and phase-aware relationships without treating candidates as current officers or inferring unnamed parties.
- Unresolved finding: the final production snapshot has not been rerun over all 71,965 historical pairs, so earlier full-history totals are superseded and must not be presented as current verification. Free-text extraction remains deliberately high-precision rather than exhaustive; ambiguous career statements, unknown proposal wording and unnamed or implicit transaction counterparties are not inferred. Person resolution remains issuer-scoped, and ShareholderMeeting identity remains disclosure-scoped, so separate NOTICE and RESULT receipts for the same physical meeting are not merged automatically.
