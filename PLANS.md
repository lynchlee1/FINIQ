# Completed Changes Requiring Follow-up

## 2026-08-24: download KIND HTML with two virtual computers

- Purpose: Make KIND external and internal HTML downloads twice as fast by appearing as two computers.
- Implementation: HTML save jobs split targets across two processes. Each process has its own HTTP session, User-Agent, per-computer 100/min limiter, local source IP when two addresses exist, and a pinned KIND destination IP when DNS returns more than one. `실행 현황` logs the `가상 컴퓨터` assignment. Stage 01 list download is unchanged.
- Verification: 83 focused backend tests pass, including two-process isolation, IP/User-Agent assignment, payload `virtual_computer_count=2`, and the existing 100/min shared-limiter regression for a single computer. Python compilation and `git diff --check` pass. Live KIND throughput was not measured in the browser; the pages were not exercised end-to-end against the network.

## 2026-08-24: restore external HTML redownload action

- Purpose: Fix the disabled `재다운로드` action shown after the all-mode external HTML inspection reports missing files together with existing files that have no hash baseline.
- Implementation: The repair target now includes owner-mode missing, invalid, hash-mismatched and hash-unverified HTML. The inspection action remains enabled for that recoverable state. Its dedicated background repair re-downloads unverified files and records fresh hashes while continuing to skip verified existing files; the normal resume path still rejects unverified reuse.
- Verification: All 189 frontend tests and 109 related backend tests pass. A focused regression proves that explicit repair re-downloads a baseline-less existing file while the ordinary resume regression remains blocked. Browser verification against the real six-mode workspace reproduces two failed modes and confirms an enabled `재다운로드` action with 71,015 owner-mode repair targets; the network download was not started. Python compilation and `git diff --check` pass. The MarketDesk production build compiles successfully and stops during TypeScript checking only at the pre-existing unsupported `modal` prop in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-24: complete structural TOC splitting and automatic correction removal

- Purpose: Split every stage-05 document completely without text-based boundaries, then remove the correction section automatically without Manual selection or mode-specific rules.
- Implementation: Stage 06 now assigns one of three verified structural schemas per document: direct heading `SECTION-N`, direct paragraph `SECTION-N`, or main-wrapper direct `xforms_title`. It includes a non-empty preamble as its own section, renders every range from a cloned source document, and only after splitting removes a section whose whitespace-compacted title contains the single token `정정`. All remaining ranges are saved together; legacy `section_save_rules` input is ignored, and the automation no longer enters `needs_review`. The parsing contract documents text-based boundary detection as a fatal failure and rejects unknown structures instead of adding a fallback.
- Verification: A read-only audit covered all 107,114 stage-05 HTML files: 32,388 heading, 994 paragraph and 73,732 XForms documents, with no unclassified, boundary-less or unparseable file. Against DB correction metadata, all 75,227 normal disclosures had zero correction matches and all 31,887 correction disclosures had exactly one; missing and multiple matches were zero, so one hardcoded token is sufficient for the current corpus. Focused backend tests pass (23 core splitter and 50 automation/web-app cases), all 189 frontend tests pass, Python compilation and `git diff --check` pass. The full backend run has one unrelated failure in an already modified external-download component assertion, and TypeScript checking reaches only the two pre-existing unsupported `modal` prop errors in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-24: audit stage 05–08 user workflows

- Purpose: Review stages 05 through 08 from the user's workflow perspective, with extra attention to existing-data inspection placement, explicit operation and fixture-backed behavior.
- Implementation: Stage 06 now exposes the active basic or derived filter directly below its top inspection card and sends that same mode identity through inspection, source listing and save. Stage 07 keeps inspection unavailable until the workspace, mode and parser method are selected. Stage 08 moves active query, search and export controls into the visible `조회 조건` card, resolves derived results from the canonical workspace path, and cancels or ignores stale list/detail requests after the source changes.
- Verification: All 189 frontend tests and 41 focused backend tests pass. Temporary-workspace fixtures prove base/derived result resolution for both change-log JSON and Excel routes without accessing the database. The MarketDesk production build compiles the changed pages and stops only at the pre-existing unsupported `modal` prop in `packages/ui/src/components/ui/select.tsx`. Browser verification confirms that 05–07 keep `기존 데이터 검토` at the top, 06 exposes and switches a derived filter without retaining the previous result, 07 waits when the parser method is missing, and 08 shows its active query/search/export controls in the main card. Python compilation and `git diff --check` pass.

## 2026-08-23: inspect external HTML storage for every mode

- Purpose: Make the top `외부 HTML 저장` inspection cover every basic and derived workspace mode, matching its position above the filter selector.
- Implementation: The external-save inspection endpoint enumerates all workspace presets and aggregates each mode's missing, invalid, hash-mismatched, unverified, and out-of-target evidence. `외부 HTML 저장` now has one `기존 원문 데이터 검사` row; when owner-mode downloads remain, that row's `검사하기` becomes `재다운로드` instead of adding a `미저장 원문 다운로드` row. Owner-only totals avoid derived-mode double counting, and the background repair processes only affected base modes before leaving the final all-mode verification visible.
- Verification: Seven focused route/repair tests, 113 related backend tests, and all 184 frontend tests pass. The repair regression proves that a failed base mode is processed once while its derived mode and a normal base mode are skipped. A DB-free, read-only run against the real workspace reports all six modes: two normal and four unavailable. The owner-only remediation total is 80,550 missing files instead of the duplicated 103,414 mode-level total. Python compilation and `git diff --check` pass. The changed MarketDesk page compiles successfully; the full Next.js build reaches only the pre-existing unsupported `modal` prop error in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-23: cancel inspections when leaving their page

- Purpose: Ensure a running existing-data inspection never survives a main-page navigation or a `세부 페이지 선택` change, including `공시원문 외부 저장`.
- Implementation: The shared inspection hook now aborts its active HTTP request on invalidation and unmount. The condition-filter and disclosure-download inspections own equivalent abort controllers; disclosure-download background inspections also request server cancellation and discard their saved polling context when the page unmounts. Existing external-save mode changes continue to abort their active request and are now covered by the inspection design contract and regression test.
- Verification: All 183 frontend tests pass and `git diff --check` passes. MarketDesk TypeScript checking reaches only the two pre-existing unsupported `modal` prop errors in `packages/ui/src/components/ui/select.tsx`; no changed file reports a type error.

## 2026-08-23: inspect all modes and repair only invalid compression files

- Purpose: Make the top compression inspection independent of the filter selected below it while keeping the inspection layout structurally stable.
- Implementation: The compression inspection enumerates every filter mode and compares each owner directory's actual saved HTML with its compressed JSON; current filter targets that have not yet been saved remain exclusively in the external-save inspection. On a repairable base-mode mismatch, the existing inspection row changes its action to `재생성`; no box or row is added. The repair job rebuilds only failed base-mode compressed files and then runs a final all-mode verification that remains visible. Derived modes inspect the same parent-owned pair without adding duplicate repair work.
- Verification: Six DB-free compression tests pass, including the real background repair API, proof that a normal mode file is not rewritten, a regression for an unsaved current-filter target, and a derived-mode owner-pair check; six existing compression service tests and all 183 frontend tests pass. A read-only run against the real workspace passes all six mode results with 253,526/253,526 mode-level records verified; it reads no database and writes comparison output only to temporary directories. Python compilation, route registration, and `git diff --check` pass. MarketDesk TypeScript checking remains blocked only by the pre-existing unsupported `modal` prop errors in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-23: separate save and compression inspection criteria

- Purpose: switching `공시원문 외부 저장` from saving to compression must replace the source-HTML inspection with inspection of the generated compressed JSON.
- Implementation summary: the detail-page switch invalidates prior evidence. Save mode keeps its existing source-file inspection, while compression mode checks `compressed-external-html.json` for format, duplicates and exact agreement with records rebuilt from the actually saved source HTML.
- Verification: all 182 frontend tests pass. Eight focused backend compression tests pass, including valid, missing and source-mismatched compressed JSON cases, and `git diff --check` passes. MarketDesk TypeScript checking remains blocked only by the pre-existing unsupported `modal` prop errors in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-13: three-mode external/internal HTML data alignment

- Purpose: align `bond_issuance`, `rights_issuance`, and `shareholder_meeting` data in stages 04 and 05 with the current year-partitioned storage and compressed-record contracts.
- Unresolved finding: two live filter/04 receipts still have no stage-05 internal HTML or manifest rows. Bond `20160819000357` and rights `20160330002146` remain in stage 03 and 04, including valid-looking external HTML, but are absent from stage 05 and 06. A full 05 run is supposed to keep requested and saved `acpt_no` sets equal. Database-linked internal re-download of those two receipts is intentionally deferred.

## 2026-08-14: shareholder-meeting entity and relationship extraction

- Purpose: turn shareholder-meeting notices and results into evidence-backed people, organizations, agendas, and phase-aware relationships without treating candidates as current officers or inferring unnamed parties.
- Unresolved finding: the final production snapshot has not been rerun over all 71,965 historical pairs, so earlier full-history totals are superseded and must not be presented as current verification. Free-text extraction remains deliberately high-precision rather than exhaustive; ambiguous career statements, unknown proposal wording and unnamed or implicit transaction counterparties are not inferred. Person resolution remains issuer-scoped, and ShareholderMeeting identity remains disclosure-scoped, so separate NOTICE and RESULT receipts for the same physical meeting are not merged automatically.
