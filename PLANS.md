# Completed Changes Requiring Follow-up

## 2026-08-27: tolerate revalidated missing KIND internal HTML sources

- Purpose: prevent a small number of permanently empty or invalid KIND source responses from keeping the entire internal HTML stage in `사용 불가` after repeated downloads.
- Implementation summary: after the normal multi-route download and direct retry fail, revalidate the affected document once through the direct KIND route. Record only a confirmed missing content path or invalid HTML response as `KIND 원본 없음` in the owner manifest and job log; connection and HTTP failures remain blocking errors. Inspections and derived-filter reuse accept a recorded exception only while its `selected_main_doc_no` is unchanged, report it separately from saved and download-required counts, and invalidate it automatically when the selected document changes. The two current source failures (`20160819000357` and `20160330002146`) were revalidated and recorded without creating placeholder HTML.
- Verification result: the live repair completed both affected owner modes and the final all-mode inspection reports 6/6 modes normal, zero owner download-required targets, and two owner `KIND 원본 없음` targets. The focused unavailable-source and external-inspection regression tests pass; the broader MarketDesk selection has 411 passed and 166 skipped with one unrelated, pre-existing utility terminology test deselected; all 197 frontend tests pass; the MarketDesk production build completes all 23 routes; and `git diff --check` passes.

## 2026-08-27: single-command MarketDesk development startup

- Purpose: start the MarketDesk backend and frontend from one repository-root command instead of keeping two terminal sessions open.
- Implementation summary: add a dependency-free development script that starts the backend, waits for its config endpoint before starting the frontend, and shuts down both process groups on exit or `Ctrl+C`. Document the command in the project README.
- Verification result: Bash syntax validation and `git diff --check` pass. With manually started servers already occupying ports 8765 and 3000, the command exits with status 1 and the expected existing-backend message without starting or stopping either user process; a full live startup remains to be exercised after those servers are stopped.

## 2026-08-27: recoverable and independent stage storage links

- Purpose: keep `단계별 저장 위치` editable when a saved target disappears or its link file is invalid, and verify that numbered stages can point to different database workspaces.
- Implementation summary: return invalid stage links as explicit per-stage status records instead of failing the entire stage-link list. The UI shows `설정 오류` while retaining `변경` and `연결 해제`; workflow path resolution remains strict and does not substitute the local stage. Preserve the existing one-link-file-per-stage design and add coverage proving `01-list` and `02-table` resolve to different target workspaces.
- Verification result: all 41 disclosure workspace tests and all 197 frontend tests pass; the MarketDesk production build compiles successfully; and `git diff --check` passes.

## 2026-08-27: separate external HTML save and compression storage

- Purpose: give 04단계 외부 HTML 원본 저장과 압축 JSON 결과에 독립적인 폴더와 단계별 저장 위치 연결을 제공한다.
- Implementation summary: keep 원본 HTML and `kind_disclosure_html_manifest.json` under `04-external-html-download/<mode>`, write `compressed-external-html.json` under `04-external-html-compress/<mode>`, and route 05단계, 07단계, 파생 필터, 검사·복구 and automation through the new compression path. Expose both 04단계 folders independently in `단계별 저장 위치`; automation now fingerprints the raw and compressed outputs separately and does not leave a compressed JSON in its raw HTML directory. Move the three production compression files only after copying and confirming byte-for-byte equality, size, and SHA-256, then remove the verified originals.
- Verification result: 124 focused workspace, automation, compression, pipeline, path, and migration tests pass; all 197 frontend tests pass; the MarketDesk production build completes with all 23 routes generated; and `git diff --check` passes. The broader MarketDesk run has 723 passed and 166 skipped; its six failures are the same pre-existing classification JSON compatibility, validation-order, and utility-page terminology assertions recorded by the previous stage-link change. The moved files retain their original sizes and SHA-256 values: bond 77,228,755 bytes (`aa302a38df544b987f5ec9cf88849b9c0f4dd0049a2c8b8fac0cd342ea648df7`), rights 120,860,547 bytes (`2f6781eb860378f86b5c9562f485c6a5efde63a3f90afbb01e987065433bb0fd`), and shareholder meeting 173,947,551 bytes (`242f85104e70a4e581a8b91fe83d7a6e01364fe152e23cdd2494358d7622a5f3`). No `compressed-external-html.json` remains under `database/04-external-html-download`.

## 2026-08-27: resumable internal HTML cancellation metadata

- Purpose: prevent successfully saved internal disclosure HTML from being reported as needing re-download after a stopped job leaves its integrity manifest stale.
- Implementation summary: finish hashing completed internal HTML after network cancellation and atomically write the partial manifest before returning the cancelled result. Align the combined validation-and-hash path with the normal validator so legacy KIND `<P>...<TABLE>` fragments receive the same valid classification. The current shareholder-meeting dataset was normalized without network access: all 116,758 stored HTML files now have SHA-256 and size metadata, while the original manifest is retained under `database/.finiq/backups`.
- Verification result: 104 focused cancellation, partial-manifest, legacy-fragment, integrity, automation, rate-limit, and web-service tests pass. A live read-only reinspection reports 142,980 targets, 116,758 hash-verified files, zero unverified/mismatched/invalid files, and 26,222 genuinely missing files; `git diff --check` passes.

## 2026-08-27: inspection result button border consistency

- Purpose: remove the mixed strong semantic borders from pale result buttons while preserving the dark primary action button.
- Implementation summary: use the shared default border token for successful and failed inspection result buttons, while retaining their semantic background and text colors and leaving the primary button variant unchanged.
- Verification result: all 197 frontend tests pass, the MarketDesk production build completes with all 23 routes generated, and `git diff --check` passes.

## 2026-08-26: stage-level disclosure workspace links

- Purpose: keep one selected disclosure workspace while placing individual `01-list` through `07-converted` stages on a different workspace, such as retaining frequently queried SQLite/filter data on SSD and moving large HTML stages to HDD.
- Implementation summary: recognize `finiq-stage-link.json` inside each canonical stage and resolve that stage to the same directory name under `target_workspace`. The marker may coexist with existing local stage data: while connected, the target stage shadows the preserved local data; removing the marker exposes the local data again. Adding a link creates the target stage directory when needed, while malformed, missing-target-workspace, and chained links fail without falling back to the local stage. When a stage is linked, its resolved path overrides stale explicit input/output paths still supplied by page settings; unlinked stages continue to preserve their explicit paths. Workspace defaults, saved path mappings, automation inputs/checkpoints, and disclosure graph sources use the resolved stage paths; stage 09 graph output remains under the selected workspace. A workspace stage-link API lists, creates, changes, and removes these links. Each numbered 01-07 page exposes only its own stage under the right-side `단계별 저장 위치`, while `공시 자동화` exposes all seven and invalidates its current plan and inspections after a change.
- Verification result: 84 focused workspace, automation, and graph tests and all 197 frontend tests pass. The focused tests cover the visible `finiq-stage-link.json` filename, linking over populated local stages, automatic target-stage creation, removal restoring the local stage, chained-link rejection, and linked 01-07 stages overriding stale explicit request paths. The MarketDesk production build completes, including TypeScript checking and generation of all 23 pages. Browser verification confirms the seven-stage automation list, the single-stage 03 page, the connection editor, and light/dark contrast. The earlier broader MarketDesk run completed with 714 passed and 166 skipped; its six failures are pre-existing classification JSON compatibility, validation-order, and utility-page terminology assertions unrelated to stage links.

## 2026-08-26: self-hosted MarketDesk fonts

- Purpose: make the MarketDesk production build independent of Google Fonts downloads and eliminate the resulting Turbopack virtual font-module resolution failure.
- Implementation summary: replace `next/font/google` with local Fontsource packages for the existing IBM Plex Sans KR and Space Grotesk families, preserving the current weights and typography. Remove the unsupported `modal` property from the shared Radix Select wrapper so the production TypeScript check can complete.
- Verification result: `npm run build:market-desk` succeeds, including TypeScript checking and static generation of all 23 pages. All 197 frontend tests and `git diff --check` pass.

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
