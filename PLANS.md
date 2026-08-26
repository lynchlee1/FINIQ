# Completed Changes Requiring Follow-up

## 2026-08-26: FINIQ-scoped WireGuard proxy lifecycle

- Purpose: prevent FINIQ's seven local `wireproxy` routes from consuming memory or maintaining VPN traffic while the MarketDesk backend is not in use.
- Implementation summary: start the configured `com.finiq.wireproxy.routeN` LaunchAgents during FastAPI startup and stop the same agents during shutdown. The local LaunchAgents now remain registered but have `RunAtLoad` and `KeepAlive` disabled, so login and process exit no longer start or revive them independently of FINIQ.
- Verification result: 113 focused lifecycle, virtual-computer, and MarketDesk web tests pass, and `git diff --check` passes. A real backend launch started all seven proxies and served traffic through route 7; graceful backend shutdown removed all seven processes and listeners.

## 2026-08-26: resilient KIND internal HTML downloads

- Purpose: prevent a transient Proton/WireGuard proxy connection failure for one disclosure from cancelling every parallel KIND internal HTML route and discarding resumable progress.
- Implementation summary: retry connection and timeout failures up to five times per target, isolate exhausted target failures so later targets continue, retry incomplete proxy-route results through the direct KIND route, and write hashes plus the partial manifest before reporting any remaining membership failure. HTML validation remains strict and no alternate parser or data source was added.
- Verification result: 71 focused internal-HTML, rate-limit, virtual-computer, automation, web-app, and web-service tests pass; the core resilience and virtual-computer suites pass with 53 tests, and `git diff --check` passes.

## 2026-08-26: legacy KIND internal HTML fragment validation

- Purpose: prevent valid historical KIND disclosure bodies without an `<html>` wrapper from being deleted and reported as invalid HTML during internal HTML download.
- Implementation summary: recognize the observed legacy body contract—a fragment beginning with `<P>` and containing a `<TABLE>`—while retaining the existing full-document and disclosure-viewer checks. Plain invalid responses remain rejected.
- Verification result: the regression test reproducing receipt `19970415M00003` passes, the live 1,566-byte KIND body is accepted by the updated validator, and the combined KIND download and disclosure pipeline resilience suites pass with 69 tests.

## 2026-08-26: rolling HTML download throughput

- Purpose: make external and internal disclosure HTML download concurrency observable from the right-dock `실행 현황` panel.
- Implementation summary: record only completed network downloads, retain their timestamps in the background job, and report `다운로드 속도` as the latest 10-second completion count multiplied by six. Existing-file skips, integrity checks, and hash work are excluded; external/internal redownload jobs use the same metric.
- Verification result: all 196 frontend tests pass. Download-rate, external-save, internal-save, and redownload backend tests pass; the combined MarketDesk backend run completed with 466 passed and 166 skipped, with one unrelated pre-existing utility-page label failure. TypeScript remains blocked by the pre-existing unsupported `modal` prop in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-26: right-dock notification clear actions

- Purpose: ensure every active right-side `알림` panel exposes the documented `지우기` action, including download inspection, automation page-count conflicts, and HTML inspection notices.
- Implementation summary: removed the shared dock's non-dismissible notification exception and added matching dismiss/reset behavior to the download page's custom dock. Clearing a notification now replaces its content with `알림 없음` and removes the semantic dock tone without changing the underlying workflow or destructive-action state.
- Verification result: all 195 frontend tests pass and `git diff --check` passes. The web-app TypeScript build remains blocked by the pre-existing `packages/ui/src/components/ui/select.tsx` use of the unsupported `modal` prop; the two reported errors do not reference this change.

## 2026-08-13: three-mode external/internal HTML data alignment

- Purpose: align `bond_issuance`, `rights_issuance`, and `shareholder_meeting` data in stages 04 and 05 with the current year-partitioned storage and compressed-record contracts.
- Unresolved finding: two live filter/04 receipts still have no stage-05 internal HTML or manifest rows. Bond `20160819000357` and rights `20160330002146` remain in stage 03 and 04, including valid-looking external HTML, but are absent from stage 05 and 06. A full 05 run is supposed to keep requested and saved `acpt_no` sets equal. Database-linked internal re-download of those two receipts is intentionally deferred.

## 2026-08-14: shareholder-meeting entity and relationship extraction

- Purpose: turn shareholder-meeting notices and results into evidence-backed people, organizations, agendas, and phase-aware relationships without treating candidates as current officers or inferring unnamed parties.
- Unresolved finding: the final production snapshot has not been rerun over all 71,965 historical pairs, so earlier full-history totals are superseded and must not be presented as current verification. Free-text extraction remains deliberately high-precision rather than exhaustive; ambiguous career statements, unknown proposal wording and unnamed or implicit transaction counterparties are not inferred. Person resolution remains issuer-scoped, and ShareholderMeeting identity remains disclosure-scoped, so separate NOTICE and RESULT receipts for the same physical meeting are not merged automatically.
