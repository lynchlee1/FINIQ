# Completed Changes Requiring Follow-up

## 2026-07-21 — Disclosure responsibility boundary correction

### Purpose

- Make Input Handling, Core Processing, and Result Validation depend on the business result declared by each document instead of a helper return value, UI state, keyword, or file's historical role.
- Re-audit every disclosure behavior against the corrected responsibility boundary.

### Implementation summary

- Rewrote the Responsibility rules around each document's declared business result and made Core Processing valid only for Core rules that produce or change its business values, membership, relationships, or ordering.
- Defined Core as the owner of business-result production and certification, and Serving as the owner of request, execution-control, and presentation lifecycles so Core Result Validation is not mistaken for Serving.
- Defined Core results as Serving inputs and reclassified every Serving display, truncation, progress, orchestration, cancellation, and recovery-routing rule from Core Processing to Input Handling.
- Defined validation metadata, manifests, warning records, and completion markers as Result Validation when they certify an unchanged completed result.
- Clarified that a prior result read by a new operation is current input, while domain extraction, result-value substitution, and incomplete-result checks are Core Processing.
- Separated invalidating an existing result and choosing a full-period input range from the normal Core download that creates replacement pages.
- Split the combined download display-count rule into missing-page display and progress-history display boundaries, and classified both as Serving Input Handling.
- Reclassified incremental search range selection as Input Handling and external HTML byte-count/SHA-256 metadata as Result Validation.
- Reordered every affected Layer/Behavior section into Input Handling, Core Processing, and Result Validation order after reclassification.
- Separated SQLite generation from manifest certification, external and internal HTML generation from manifest metadata linking, and HTML input conversion from domain-value extraction helpers.
- Split filtered-input validation from external HTML result-field extraction, and graph-input validation from graph event-date production.
- Corrected ambiguous responsibility labels for result publication, manifest linking, saved-result lookup, progress-event input, section-title extraction, rights-issuance type extraction, and graph event-date production.
- Documented reduced graph generation after missing disclosure or company identifiers as a Core Processing Fallback.
- No files under `resources/` were read or changed.

### Verification result

- Confirmed all 20 disclosure README documents retain the same 11-heading classification structure and explicit `없음` markers for empty categories.
- Confirmed all 221 behavior entries use exactly one allowed responsibility label: 97 Input Handling, 100 Core Processing, and 24 Result Validation.
- Confirmed no Serving behavior is classified as Core Processing.
- Confirmed every Layer/Behavior section follows Input Handling → Core Processing → Result Validation order.
- Confirmed every one of the 201 adjacent behavior-entry pairs has exactly one correctly placed `<br>` separator.
- Confirmed all relative Markdown links and referenced anchors resolve.
- `git diff --check` and the `resources/` scope check passed. Runtime tests were not run because the change is documentation-only.

## 2026-07-20 — Disclosure behavior classification rewrite

### Purpose

- Rewrite every disclosure behavior document against `docs/behavior-classification-rules.md` and make classification boundaries explicit.
- Preserve every empty behavior category with its heading and an explicit `없음` entry.

### Implementation summary

- Standardized all 20 disclosure README documents as `Core` and `Serving`, each divided into `Feature`, `Fallback`, and `Shutdown`, and labeled every behavior with `Input Handling`, `Core Processing`, or `Result Validation` responsibility.
- Added the shared classification boundary to the disclosure parent document and separated normal selection, exclusion, empty-result, default-value, and review-wait behavior from unexpected-failure recovery and termination.
- Reclassified normal download defaults and correction-history value judgments as Features; classified full-period redownload, per-file parser exclusion, retries, reduced graph relationships, and display recovery as Fallbacks; and kept unsafe or incomplete execution paths as Shutdowns.
- Split mixed rules where validation, recovery, and termination had previously shared one entry, including existing-result validation, parser `skip_errors`, preview augmentation, required bond-table selection, graph input discovery, and stored-result validation.
- Re-audited the responsibility and layer boundaries after the initial rewrite: moved pre-execution KIND and pagination reads to Input Handling, separated HTML input parsing from row/result generation, treated parser warning and family checks as Core Processing, limited Result Validation to completed outputs, and moved automation orchestration from Core to Serving.
- Moved normal exclusions and default-value selection out of failure handling, including legacy preset exclusion, graph display-name priority, and correction-history threshold defaults; split the matching failure paths into their own Fallback or Shutdown rules.
- Added the complete Serving taxonomy to mode-specific parser documents and wrote `없음` in every empty Core or Serving category.
- Standardized `<br>` separators between every pair of adjacent behavior entries, including pairs separated by Feature, Fallback, Shutdown, Core, or Serving headings, and placed each separator directly after the preceding behavior content so Markdown renders it consistently.
- No files under `resources/` were read or changed.

### Verification result

- Confirmed all 20 disclosure README documents contain the same 11-heading classification sequence and no legacy `Features`, `Fallbacks`, or `Shutdowns` headings.
- Confirmed every behavior entry has one allowed responsibility label and every otherwise-empty category contains `없음`.
- Rechecked all 211 behavior entries against the three classification questions and cross-checked equivalent input, intermediate-result, completed-result, display, retry, and termination rules across documents.
- Confirmed all 191 adjacent behavior-entry pairs have exactly one `<br>` separator in the canonical `content → <br> → blank line → next heading` layout.
- Confirmed all relative Markdown links and referenced anchors in the 20 disclosure README documents resolve.
- `git diff --check` and the `resources/` scope check passed. Runtime tests were not run because the change is documentation-only.

## 2026-07-20 — Coding-style instruction relocation

### Purpose

- Make repository coding-style instructions directly available to coding agents.

### Implementation summary

- Moved the complete Coding style section from `docs/README.md` into `AGENTS.md` and merged it with the existing fallback guidance.
- Left the Writing style guidance and examples in `docs/README.md` unchanged.

### Verification result

- Confirmed the moved rules occur in `AGENTS.md` and no longer occur in `docs/README.md`.
- `git diff --check` passed for the three edited Markdown files.

## 2026-07-18 — Incremental filter review fixes

### Purpose

- Correct the implementation errors confirmed by the incremental-filter review.

### Implementation summary

- Exposed the condition-search card for automation ranges beginning at stages 04–07, where profile validation requires a saved preset.
- Preserved the pre-run canonical workflow when cancellation occurs before any source row is inspected.
- Rejected fractional incremental counts and required exact boolean `complete=false` and `passed=false` flags on interrupted results.
- Restored the missing workspace path contract, corrected the stale parser-documentation route, and removed trailing whitespace that invalidated the recorded diff check.

### Verification result

- `118 passed`: disclosure Web app, workspace, and automation suites.
- `35 passed`: focused disclosure filter service tests.
- `19 passed`: frontend path/layout contract tests.
- Python compile, TypeScript type-check, `git diff --check`, and the local Markdown-link check for 33 files passed.

## 2026-07-18 — Incremental disclosure filter workflow

### Purpose

- Keep each stage 03 condition, execution state, completed result, and interrupted partial result in one canonical workflow JSON.
- Reuse the previously inspected source count so recurring runs filter only newly appended stage 02 rows.
- Fail explicitly when source-count integrity or saved-condition integrity no longer holds.

### Implementation summary

- Embedded completed and interrupted filter results in `<data_root>/03-filter/<workflow-name>.json`; same-condition saves preserve them, while condition or mode changes reset the workflow.
- Added source offsets to the SQLite reader, count-regression checks, explicit search denominator/result numerator fields, interrupted partial-result capture, contiguous merge checks, duplicate receipt-number checks, and atomic replacement after a successful temporary merge.
- Kept `<mode>/filtered.json` as a derived stage 04 compatibility file and connected both the manual filter route and disclosure automation stage 03 to the same canonical workflow contract.
- Required automation runs from stage 03 onward to identify a saved condition-search preset and reject runtime mode or condition conflicts.
- Added the `중단됨` workflow state to the existing UI terminology and documented the count-only, append-order integrity assumptions and the deliberate absence of an unverifiable historical membership hash.
- No files under `resources/` were read or changed for this implementation.

### Verification result

- `111 passed`: disclosure Web app, workspace, and automation suites.
- `33 passed`: focused disclosure filter service tests.
- `18 passed`: frontend path/layout contract tests.
- TypeScript type-check and Python compile checks passed.

## 2026-07-17 — Documentation hierarchy normalization

### Purpose

- Match the disclosure 08, 09, and parent README structure to the established disclosure document format.
- Move rules shared by disclosure stages into `docs/disclosures/README.md` so stage documents contain only stage-specific paths, values, and behavior.
- Move rules shared by Ontology pages into `docs/ontology/README.md` and remove the same rules from child documents.

### Implementation summary

- Rebuilt the disclosure parent README with the standard Summary, Features, Fallbacks, Shutdowns, and Serving sections; normalized the 08 and 09 heading levels and moved the 09 data format under Summary details.
- Centralized the disclosure workspace and separate-directory settings, mode isolation, shared HTML reuse test, diagnostic-display contract, common job state, cancellation, empty-value display, worker default, settings persistence, and shared configuration failures.
- Left only stage-specific display counts and input/output contracts in the stage documents, moved correction-history browser rules from stage 00 to stage 08, and moved Ontology/Quantiwise display rules out of the disclosure automation document.
- Moved the former Ontology common document's rules into `docs/ontology/README.md`, added shared shard-path, worker, job-state, display, and settings rules there, and reduced `docs/ontology/common/README.md` to a compatibility link.
- Removed child duplicates for shard path resolution, missing-shard shutdown, company metadata merging, and the default date range. No files under `resources/` were read or changed.

### Verification result

- The disclosure format check confirmed that the parent, 08, and 09 documents have the same seven-heading sequence as stages 00–07.
- The parent-rule audit confirmed the selected disclosure and Ontology common rules exist in their parent document and each audited rule appears in only one file.
- All 13 disclosure Serving sections retain bold `Feature`, `Fallback`, and `Shutdown` groups in order with no nested level-four heading.
- `git diff --check` and the local Markdown-link check for all files under `docs/` passed.

## 2026-07-17 — Fallback logic documentation audit

### Purpose

- Reverify fallback and alternative-path behavior against the current code and document every reachable mechanism that was not already described under `docs/`.
- Make output loss, partial results, compression/display limits, substitutions, recovery paths, and failure boundaries explicit without changing runtime behavior.

### Implementation summary

- Updated the matching disclosure-stage and ontology README files with current behavior classified under `Features`, `Fallbacks`, or `Shutdowns`.
- Added parser and selector recovery, missing-field substitution, partial-result handling, compatibility inputs, retry and serial recovery, default source and period selection, transactional restoration, display/diagnostic limits, and lossy normalization rules.
- Reclassified frontend-only display, browser-state, and in-browser calculation behavior under `docs/disclosures/README.md`; backend response limits, stored-output behavior, parser rules, and export-affecting graph state remain in their owning stage or ontology documents.
- Rechecked two previously reported candidates against the current code and did not document them as active fallbacks: missing parse results are no longer cached as `{}`, and records without a usable sequence are skipped before the later sort default can be reached.
- Removed the previously documented random edge-ID branch after confirming that the current graph validation flow supplies missing IDs and rejects duplicate IDs before the later normalizer, making that branch unreachable for accepted graph input.
- Made documentation-only changes. No files under `resources/` were read or changed.

### Verification result

- `31 passed`: KIND JSON conversion and company classification tests.
- `2 passed`: source-preview and existing-download validation tests.
- `2 passed`: Quantiwise preview and invalid-date continuation tests. One dependency deprecation warning was reported.
- `37 passed`: focused frontend tests for correction-history display logic, fallback boundaries, ontology workspaces, and the asset Excel utility.
- `git diff --check` and the local Markdown-link check passed.

## 2026-07-17 — Policy-inconsistent fallback removal

### Purpose

- Remove newly documented fallbacks that silently alter, omit, truncate, or partially return data and therefore conflict with the repository policy of retaining only correctness- or reliability-preserving recovery.
- Keep frontend-only presentation behavior in the disclosure automation document while keeping parser, storage, and backend behavior in its owning disclosure or ontology document.

### Implementation summary

- Removed correction-matrix neighbor filling, permissive date and number salvage, the browser Triple Barrier 120-marker cap, and falsy-value display paths that hid numeric zero.
- Rejected unknown KIND search conditions, unknown saved filters, invalid canonical result-page filenames, unusable external compressed records, legacy singular merge inputs, populated invalid preview dates, dangling ontology edges, and invalid relationship weights instead of silently substituting or omitting values.
- Changed missing manifest shards, existing-download path/read errors, and market-unknown mapping-only rows under a specific market filter from partial or widened results to explicit failure or exclusion.
- Preserved an explicit company count of zero and stopped Neo4j synchronization from inventing risk metadata when the source value is null.
- Retained retries, transaction restoration, cache recomputation, bounded diagnostic display, parser recovery required for malformed KIND HTML, and serial recovery after process-pool failure because they preserve integrity without fabricating accepted output.
- Removed the raw KIND disclosure-field compatibility input; `disclosure_type_groups` is now the only accepted disclosure-type request contract, including saved workflow snapshots.
- Changed unreadable saved search conditions and broken result-page pagination from mismatch/partial-result states to explicit failures.
- Removed sectionless table-row promotion, ragged-row right padding, the 1 MiB workflow-format scan limit, receipt-number and legacy-record year inference, and the external HTML compressor's second decoder/parser pass.
- Kept the shared KIND HTML recovery parser as the single canonical reader; the external compression path now consumes that reader's result once instead of maintaining a separate recovery implementation.
- Removed partial viewer-metadata compression: external compression now requires `acptNo`, both document selects, non-empty document numbers for every option, and a selected main document instead of dropping incomplete options. Removed only the 100-byte minimum from existing-HTML detection; its identifier check and reuse behavior remain unchanged.
- Updated the owning fallback documents and focused regression tests. No files under `resources/` were read or changed.

### Verification result

- `159 passed`: focused Python suites for fallback policy, Neo4j synchronization, ontology, Quantiwise assets, integrated merge, company classification, and KIND web behavior.
- `91 passed`: KIND download, JSON conversion, result-folder exploration, company classification, pagination, and the focused fallback-policy tests after the second removal pass.
- `91 passed`: disclosure web-app, automation, and disclosure-time metadata tests.
- `486 passed, 1 deselected`: KIND web-service regression suite excluding one pre-existing cancellation callback-count test unrelated to these changes. The four fixtures that still assumed removed table correction behavior passed after being changed to canonical table structure.
- `63 passed`: KIND HTML conversion and download tests after strict viewer-metadata compression and removal of the existing-HTML 100-byte minimum.
- `10 passed`: focused fallback-policy tests, including strict selected-document validation and the single shared viewer reader.
- `35 passed, 452 deselected`: focused external HTML, viewer metadata, and compression web-service tests.
- `39 passed`: focused frontend suites for fallback boundaries, correction history, ontology workspaces, and the asset Excel utility.
- Graph viewer package build and market-desk TypeScript no-emit check passed.
- Python bytecode compilation, `git diff --check`, the local Markdown-link check for 14 changed Markdown files, and the `resources/` scope check passed.
