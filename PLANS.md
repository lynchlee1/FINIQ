# Completed Changes Requiring Follow-up

## 2026-08-23: distinguish bundled HTML inspection results from independent steps

- Purpose: `공시원문 외부 저장` used one inspection request for existing-file integrity and pending-download counts but displayed the result rows as numbered independent steps.
- Implementation summary: inspection steps can now opt out of sequence numbering. The external HTML save inspection marks both bundled rows unnumbered, keeps the inspection action only on the first row, and leaves the pending-download row actionless in its initial waiting state. The shared design contract now requires numbered rows to run independently and bundled rows to leave the number area blank.
- Verification: the two focused bundled-inspection regressions pass, and all four external-HTML metadata-warning tests pass. The running development server returned HTTP 200 for `/external-html-download`, and `git diff --check` passes. Repository-wide TypeScript checking remains blocked only by the pre-existing unsupported `modal` prop in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-23: preserve completed metadata inspection after applying saved settings

- Purpose: `저장된 설정 적용` cleared the completed metadata result and forced `공시내역 다운로드` to restart inspection from the first step.
- Implementation summary: metadata completion is now keyed only to the data path used to discover metadata. Search-setting changes invalidate file/KIND evidence but preserve the metadata result, and the settings comparison is recomputed locally. The API now reports whether every saved range uses the same filter settings so the repair action is offered only when applying one saved setting is valid.
- Verification: the focused frontend regression passes, 34 existing-download backend tests pass, and 26 adjacent frontend tests pass. A direct Next.js development load compiled `/download` and returned HTTP 200; the full click-through could not call the download API because the local backend was not running. Repository-wide TypeScript checking remains blocked by the pre-existing unsupported `modal` prop in `packages/ui/src/components/ui/select.tsx`.

## 2026-08-23: organize design documentation by component

- Purpose: allow components with additional design contracts to grow without expanding one root design file.
- Implementation summary: moved the shared design system and UI terminology to `design/README.md`, moved the inspection-block contract to `design/components/inspection-block.md`, and added `design/components/README.md` as the component-document index. Updated repository instructions, review guidance, terminology tests and plan references to the new paths.
- Verification: focused terminology tests pass, repository search finds no remaining references to the removed root design filenames, all relative Markdown links in `design/` resolve, and `git diff --check` passes.

## 2026-08-23: document inspection-block state preservation and placement

- Purpose: prevent a repair action such as `저장된 설정 적용` from discarding a completed metadata inspection and forcing the user to restart the entire inspection block.
- Implementation summary: added `design/components/inspection-block.md` as the single contract for ordered steps, evidence-bound invalidation, repair behavior, asynchronous result protection, page placement and regression scenarios. Moved the `세부 페이지 선택`/top-of-page placement rule out of `design/README.md`, which now links to the dedicated contract. The download feature contract now requires settings application to preserve metadata and continue from file inspection.
- Verification: documentation checks confirm that the dedicated design contains the state-preservation invariant, the exact settings-mismatch recovery scenario, and both page-placement branches. No production behavior was changed by this documentation-only update.

## 2026-08-23: run download inspection steps in listed order

- Purpose: clicking `검사하기` on `메타데이터 읽기` also started `저장 파일 구성 검사`, so steps 1 and 3 ran together.
- Implementation summary: step 1 now calls `detect-existing` only. File composition and KIND stay on a later `검사하기` that appears on `저장 파일 구성 검사` after metadata and settings pass. The files step stays `대기` while metadata is running.
- Verification: headless Chrome on `/download` clicked step-1 `검사하기`. The page called `/api/download/detect-existing` only, not `inspect-folder`. After metadata completed, `저장 파일 구성 검사` stayed `대기` (`설정 불일치를 먼저 해결해야 합니다.`) and `KIND 건수 비교` stayed `대기`.

## 2026-08-23: keep overall inspection verdict off 정상 while steps remain

- Purpose: `기존 데이터 검토` showed a green `정상` header while a later step was still open, especially `미저장 원문 다운로드` on HTML save pages.
- Implementation summary: the overall verdict is `정상` only after every page-owned step has passed. A remaining extra step keeps the header at `검사 중` while the passed row can still show `정상`. Re-running 01 no longer leaves later rows green from the previous result.
- Verification: unit/source checks cover `remainingInspection` plus `stepState` on the HTML save card. Click-through of a live inspect with pending downloads was not run against a restarted API.

## 2026-08-23: keep 기존 데이터 검토 as the first content card

- Purpose: `기존 데이터 검토` must always be the top content card on numbered disclosure workflow pages. The previous layout experiment that put search or filter cards above it is rejected.
- Implementation summary: restored `공시내역 다운로드` and `공시원문 외부/내부 저장` so the review card is first after `세부 페이지 선택`. `design/components/inspection-block.md` now owns the hard page-order rule: only `세부 페이지 선택` may sit above the review; search, filter, path, and execution cards always follow it.
- Verification: headless Chrome on the running market-desk (`127.0.0.1:3000`) showed `기존 데이터 검토` as the first content card on `/download`, `/internal-html-download`, `/table`, `/html-parse`, and `/html-section-split`. `/external-html-download` has `세부 페이지 선택` then `기존 데이터 검토`. `/filter` opens in `공시내역 제목 검색`, which still does not render the review card. `검사하기` click-through was not run.

## 2026-08-23: derived-filter HTML inspection reports missing parent files

- Purpose: inspecting a 파생 필터 on `공시원문 외부 저장` failed with an English exception when parent HTML was incomplete, instead of a structured 사용 불가 result.
- Implementation summary: derived-filter folder inspection now returns missing/invalid/hash counts from the parent-owned directory without raising, and never treats parent extras as deletion candidates. Download still refuses to fetch. The page treats 상위 필터에 없는 원문 as 사용 불가 and does not offer 재다운로드.
- Verification: unit tests cover inspect-with-missing, inspect-with-hash-mismatch, and download still raising `cannot be reused`. Live `bond_issuance_kosdaq` is missing parent HTML for 2026-05 onward, including the reported receipts; those files must be saved from `bond_issuance` first.

## 2026-08-22: show all saved filters when opening 조건검색 필터

- Purpose: on `공시원문 외부 저장`, opening `조건검색 필터` showed 2 of 6 saved filters because the selected name was treated as a search query.
- Implementation summary: `FilterPresetCombobox` now lists every preset while a saved identity is selected, and still filters only while the user is typing.
- Verification: live workspace has 6 filters and `html_parse_mode=rights_issuance`. Opening the dropdown in headless Chrome showed all 6 options, including the three parent filters and their `*_kosdaq` children.

## 2026-08-22: unify 공시원문 외부 저장 filter dropdown and inspection order

- Purpose: make `공시원문 외부 저장` follow `design/README.md` by reusing the `공시내역 필터링` typeable `조건검색 필터` dropdown, and by placing `기존 데이터 검토` immediately after `세부 페이지 선택`.
- Implementation summary: exported the shared `FilterPresetCombobox` and used it on the HTML download page with create disabled; moved the inspection card above the filter card after the mode switch; documented the numbered-workflow page order in `design/components/inspection-block.md`.
- Verification: the running market-desk page at `/external-html-download` compiled (HTTP 200). The client bundle renders `WorkflowModeSwitch`, then `기존 데이터 검토`, then the shared `FilterPresetCombobox` instead of a native `<select>`. No browser tools were available, so the open dropdown and click path were not exercised in the UI.

## 2026-08-13: three-mode external/internal HTML data alignment

- Purpose: align `bond_issuance`, `rights_issuance`, and `shareholder_meeting` data in stages 04 and 05 with the current year-partitioned storage and compressed-record contracts.
- Unresolved finding: two live filter/04 receipts still have no stage-05 internal HTML or manifest rows. Bond `20160819000357` and rights `20160330002146` remain in stage 03 and 04, including valid-looking external HTML, but are absent from stage 05 and 06. A full 05 run is supposed to keep requested and saved `acpt_no` sets equal. Database-linked internal re-download of those two receipts is intentionally deferred.

## 2026-08-14: shareholder-meeting entity and relationship extraction

- Purpose: turn shareholder-meeting notices and results into evidence-backed people, organizations, agendas, and phase-aware relationships without treating candidates as current officers or inferring unnamed parties.
- Unresolved finding: the final production snapshot has not been rerun over all 71,965 historical pairs, so earlier full-history totals are superseded and must not be presented as current verification. Free-text extraction remains deliberately high-precision rather than exhaustive; ambiguous career statements, unknown proposal wording and unnamed or implicit transaction counterparties are not inferred. Person resolution remains issuer-scoped, and ShareholderMeeting identity remains disclosure-scoped, so separate NOTICE and RESULT receipts for the same physical meeting are not merged automatically.
