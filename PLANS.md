# Completed Changes Requiring Follow-up

## 2026-08-26: align KIND route count and direct-route indexing

- Purpose: Remove the fixed eight-route claim and make the direct connection read as part of the same indexed KIND route list.
- Implementation: The backend and Web settings now derive the total KIND route limit from the current CPU count, with one direct route plus up to CPU-count-minus-one localhost proxies. The UI reports that live CPU count, applies it to `경로 추가`, and renders the fixed direct connection as route 0 using the same index and content alignment as proxy routes.
- Verification: 105 focused backend tests and all 194 frontend tests pass; `git diff --check` passes. Browser verification on the saved four-proxy configuration reports the live eight-CPU limit, renders direct access as route 0, and measures identical index/content alignment and row height across routes 0–4. No route setting was saved and no external connection check was triggered.

## 2026-08-25: keep incomplete internal HTML inspection non-green

- Purpose: Prevent `기존 원문 데이터 검사` from showing the green `정상` state when its own summary reports target HTML files that still need to be downloaded.
- Implementation: Added the warning-colored `다운로드 필요` inspection-step state and use it for internal HTML inspections while target downloads remain. The overall card continues to stay at `검사 중`, and the separate download action remains available.
- Verification: The focused regression test and all 194 frontend tests pass; `git diff --check` passes.

## 2026-08-25: skip compression modes without source HTML

- Purpose: Prevent modes with no saved source HTML from appearing as broken compression files or regeneration targets.
- Implementation: Compression inspection now marks source-empty modes as `압축 안 함` and excludes them from failures and repairs. Mixed workspaces regenerate only failed modes that actually have source HTML, while the UI reports normal, skipped, and failed mode counts separately.
- Verification: Eight focused backend tests and all 193 frontend tests pass; `git diff --check` passes. A read-only inspection of the real workspace reports all six base/derived modes normal with 414,626 mode-level records verified and no missing, unexpected, or duplicate records. The stale `2개 모드 재생성 필요` result is absent in a fresh local page session, and the development backend was restarted on the changed code.

## 2026-08-25: compact the KIND network-route inspector

- Purpose: Replace the tall repeated route form with a dense settings list that fits the existing right inspector and makes editing, verification state, and save readiness immediately legible.
- Implementation: Grouped each route's number, editable proxy address, public-IP result, and delete action into one compact row separated by a single divider. Public IP and its state share one line, such as `공인 IP: 정상(84.233.167.238)`, instead of repeating a detached right-side status. Typography now uses only the documented 14px Body scale for route controls and the 12px Caption scale for headings, explanations, indices, IP results, and summaries; hierarchy comes from weight and semantic color instead of extra font sizes. The fixed direct route uses the same alignment without looking editable. The section header now owns the aggregate `검사 필요` or checked-count state, `경로 추가` is a small secondary action, and `변경사항 저장` is disabled until the normalized route list differs from saved settings. Any add, edit, or removal clears all prior IP evidence because uniqueness is a whole-list property.
- Verification: The focused route UI tests and all 193 frontend tests pass; `git diff --check` passes. Browser verification on the real four-proxy configuration measures the section at about 516px high, confirms the unchanged list disables saving, a route edit enables saving while retaining `검사 필요`, and both light and dark themes preserve alignment and contrast. No route setting was saved and no external connection check was triggered during visual verification.

## 2026-08-24: manage provider-neutral KIND network routes in relevant Web settings

- Purpose: Let users configure and verify the multiple public-IP paths used by KIND work from the relevant Web UI without tying FINIQ to ProtonVPN or showing the control on unrelated pages.
- Implementation: Added one shared `KIND 네트워크 경로` section to the right settings panels of `공시원문 외부 저장`, `공시원문 내부 저장`, and `공시 자동화` only. Direct access stays fixed, up to seven localhost HTTP proxy endpoints can be added or removed, and saving remains explicit. A new provider-neutral check endpoint tests the unsaved direct/proxy routes concurrently through one public-IP lookup, reports each public IP, marks connection failures and duplicate IPs, and never falls back to the direct route.
- Verification: 14 focused backend tests and all 193 frontend tests pass; `git diff --check` passes. A live check reports five ready routes and five distinct public IPs for direct access plus ports 25001-25004. Browser verification confirms the section appears once on each of the three intended workflows, is absent from `공시원문 목차 분리`, and remains readable in both light and dark themes. The MarketDesk production build compiles successfully and stops during TypeScript checking at the pre-existing unsupported `modal` prop in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-24: replace simulated KIND computers with explicit IP egresses

- Purpose: Make the KIND HTML split-download feature use genuinely distinct public-IP paths and scale from one through five routes without pretending that local or destination IP aliases are separate computers.
- Implementation: Replaced source-address binding, destination-DNS pinning, User-Agent variation and multiprocessing with one direct route plus up to seven explicitly configured localhost HTTP CONNECT proxies, matching this computer's eight CPU cores. Every route owns its HTTP sessions, request spacing and per-minute limiter; the configured `max_workers` total is divided exactly across active routes, all years are dispatched in one job, and a failed proxy is never retried over the direct route. Settings, detail-page jobs, redownloads and disclosure automation now carry the validated `kind_proxy_urls` list. The reference documents the minimal Proton WireGuard + `wireproxy` setup without storing or reading VPN keys.
- Verification: 91 focused backend tests and all 191 frontend tests pass; Python compilation and `git diff --check` pass. The full backend run completes with 1,407 passed and 167 skipped; its six failures are in unchanged classification-path, input-validation-order and HTML-parser UI-contract behavior. The MarketDesk production build compiled the changed pages and then stopped at the pre-existing unsupported `modal` prop in `packages/ui/src/components/ui/select.tsx`. Four Proton WireGuard routes run through `wireproxy` on localhost ports 25001–25004; all four reach KIND with HTTP 200, have distinct public IPs, and differ from the direct route.

## 2026-08-24: download KIND HTML with two virtual computers

- Status: Superseded the same day by explicit direct/proxy egress routing above.
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
