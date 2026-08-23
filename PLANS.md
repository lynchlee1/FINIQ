# Completed Changes Requiring Follow-up

## 2026-08-23: separate save and compression inspection criteria

- Purpose: switching `공시원문 외부 저장` from saving to compression must replace the source-HTML inspection with inspection of the generated compressed JSON.
- Implementation summary: the detail-page switch invalidates prior evidence. Save mode keeps its existing source-file inspection, while compression mode checks `compressed-external-html.json` for format, current-filter membership, duplicates and exact agreement with records rebuilt from the source HTML.
- Verification: all 182 frontend tests pass. Eight focused backend compression tests pass, including valid, missing and source-mismatched compressed JSON cases, and `git diff --check` passes. MarketDesk TypeScript checking remains blocked only by the pre-existing unsupported `modal` prop errors in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-13: three-mode external/internal HTML data alignment

- Purpose: align `bond_issuance`, `rights_issuance`, and `shareholder_meeting` data in stages 04 and 05 with the current year-partitioned storage and compressed-record contracts.
- Unresolved finding: two live filter/04 receipts still have no stage-05 internal HTML or manifest rows. Bond `20160819000357` and rights `20160330002146` remain in stage 03 and 04, including valid-looking external HTML, but are absent from stage 05 and 06. A full 05 run is supposed to keep requested and saved `acpt_no` sets equal. Database-linked internal re-download of those two receipts is intentionally deferred.

## 2026-08-14: shareholder-meeting entity and relationship extraction

- Purpose: turn shareholder-meeting notices and results into evidence-backed people, organizations, agendas, and phase-aware relationships without treating candidates as current officers or inferring unnamed parties.
- Unresolved finding: the final production snapshot has not been rerun over all 71,965 historical pairs, so earlier full-history totals are superseded and must not be presented as current verification. Free-text extraction remains deliberately high-precision rather than exhaustive; ambiguous career statements, unknown proposal wording and unnamed or implicit transaction counterparties are not inferred. Person resolution remains issuer-scoped, and ShareholderMeeting identity remains disclosure-scoped, so separate NOTICE and RESULT receipts for the same physical meeting are not merged automatically.
