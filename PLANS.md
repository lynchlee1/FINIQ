# Completed Changes Requiring Follow-up

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
