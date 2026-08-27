# FINIQ MarketDesk Design System

컴포넌트별 상세 계약은 [컴포넌트 디자인](./components/README.md)에 모은다. 이 문서는 공통 시각 체계와 UI 용어의 단일 기준이다.

## 1. Atmosphere & Identity

FINIQ MarketDesk is a quiet analyst cockpit: dense, exact, and calm under noisy market data. The signature is a slate terminal surface with restrained blue focus states and tabular numeric rhythm, so disclosure events, price data, and model labels feel auditable rather than decorative.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
| --- | --- | --- | --- | --- |
| Surface/primary | `--background` | `#f8fafc` | `#0d1117` | Main app background |
| Surface/card | `--color-card` | `#ffffff` | `#161b22` | Cards, analysis panels |
| Surface/muted | `--color-muted` | `#f1f5f9` | `#21262d` | Subtle metric blocks, table headers |
| Surface/input | `--surface-input` | `#ffffff` | `#0d1117` | Inputs, selects, table body |
| Text/primary | `--foreground` | `#0f172a` | `#f0f6fc` | Primary copy |
| Text/secondary | `--color-muted-foreground` | `#64748b` | `#8b949e` | Captions, help text |
| Border/default | `--color-border` | `#e2e8f0` | `#30363d` | Dividers and panel outlines |
| Accent/primary | `--color-primary` | `#0f172a` | `#2f81f7` | Primary actions and focus |
| Status/success | `--status-success` | `#15803d` | `#3fb950` | Completed rows, positive labels |
| Status/warning | `--status-warning` | `#b45309` | `#d29922` | Reused or partial runs |
| Status/error | `--color-destructive` | `#dc2626` | `#ef4444` | Failed rows, API errors |

### Rules

- Blue is reserved for active controls, focus, and primary execution. Do not use it as ambient decoration.
- Right-dock semantic colors are limited to green for successful completion, amber for running work, attention, or user action, and red for errors. An active `실행 현황` or `알림` control always uses one of those tones. There is no gray notification state. Inactive controls and `알림 없음` retain the default control styling with no semantic tone.
- Tables and metrics use tonal shift first, borders second, and shadows never.
- Raw hex values should stay in `globals.css` tokens or legacy compatibility classes; new UI should prefer token-backed Tailwind colors already used in the app.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
| --- | --- | --- | --- | --- | --- |
| H1 | 24px | 650 | 1.25 | 0 | Workflow page titles |
| H2 | 18px | 650 | 1.35 | 0 | Panel titles |
| H3 | 15px | 600 | 1.4 | 0 | Section titles |
| Body | 14px | 400 | 1.55 | 0 | Standard controls and rows |
| Body/sm | 13px | 400 | 1.45 | 0 | Secondary explanations |
| Caption | 12px | 500 | 1.35 | 0.02em | Labels and metadata |
| Numeric | 13px | 500 | 1.4 | 0 | Tabular financial values |

### Font Stack

- Primary: IBM Plex Sans KR, Inter fallback, system UI.
- Mono: Space Grotesk, SFMono-Regular, monospace.

### Rules

- Financial values use tabular numerals.
- Korean workflow labels stay concise and reuse the UI terminology contract below.
- Avoid oversized hero typography; MarketDesk is an operational platform, not a marketing page.

## 4. Spacing & Layout

### Base Unit

All spacing derives from a base of 4px.

| Token | Value | Usage |
| --- | --- | --- |
| `--space-1` | 4px | Icon-to-label, tight table cells |
| `--space-2` | 8px | Inline controls, compact gaps |
| `--space-3` | 12px | Form field groups |
| `--space-4` | 16px | Card inner spacing |
| `--space-5` | 20px | Panel group spacing |
| `--space-6` | 24px | Major card padding |
| `--space-8` | 32px | Section breaks |

### Grid

- Max content width: 1280px via the existing app shell.
- Operational pages use stacked full-width bands first; two-column layouts are reserved for controls next to live result panels.
- Tables may overflow horizontally inside a contained scroll region, never the page.

### Rules

- Use compact controls for analyst workflows; avoid empty cards that do not change decisions.
- Summary cards must show decision-making values such as total, completed, failed, created, reused, or active parameter hash.
- Existing-data inspection behavior and page order follow [components/inspection-block.md](./components/inspection-block.md).

## 5. Components

### Analysis Panel

- **Structure**: card header with title and concise context, then controls or data.
- **Variants**: execution setup, result review, event selection.
- **Spacing**: `--space-4` inner groups, `--space-5` between major groups.
- **States**: loading skeleton/spinner, empty copy, inline error copy.
- **Accessibility**: labels on every input/select; buttons disable while running.
- **Motion**: no layout motion; hover/focus only.
- **Disclosure workflow form rhythm (01-07)**: primary inputs, selects, and action buttons are 40px high; labels sit 8px above their controls; peer fields and card content groups use 16px gaps; top-level cards use the shared 16px header/content inset and 24px page gap. Right-dock inspector controls remain the documented compact 32px variant.

### Data Integrity Inspection Panel

- [components/inspection-block.md](./components/inspection-block.md) is the source of truth for structure, state transitions, repair behavior, page order, responsive behavior and required regression scenarios.

### Segmented Mode Control

- **Structure**: two or three buttons in a bordered row.
- **Reuse**: page-level workflow mode controls use the shared `WorkflowModeSwitch`; the component owns track/button styling and the `--space-3` gap to its content. Pages provide only options, current value and state updates.
- **Variants**: active tonal fill, inactive transparent.
- **Spacing**: `--space-1` button gap, `--space-2` horizontal padding.
- **Layout**: the containing track should hug its options on desktop and become full-width only when mobile space requires it. Do not wrap a compact mode control in an otherwise empty full-width card. Inspection-block placement follows [components/inspection-block.md](./components/inspection-block.md).
- **States**: hover, active, focus visible.
- **Accessibility**: use `aria-pressed` for active mode.
- **Motion**: 150ms color transition.

### Result Table

- **Structure**: sticky mental model of header, horizontal scroll container, compact rows.
- **Variants**: stored results, selected event list.
- **Spacing**: `--space-2` vertical cell padding, `--space-3` horizontal cell padding.
- **States**: empty, failed-row status, completed-row status.
- **Accessibility**: semantic table, visible status text, no color-only meaning.
- **Motion**: none.

## 6. Motion & Interaction

| Type | Duration | Easing | Usage |
| --- | --- | --- | --- |
| Micro | 120ms | ease-out | Button hover and active state |
| Standard | 200ms | ease-in-out | Mode switch color changes |

### Rules

- Only animate `transform` and `opacity` for any future motion.
- Focus rings are required for inputs, selects, and mode buttons.
- Loading states must preserve layout height to avoid result table jumps.

## 7. Depth & Surface

### Strategy

Borders plus tonal shift.

| Type | Value | Usage |
| --- | --- | --- |
| Default border | `1px solid var(--color-border)` | Cards, tables, mode controls |
| Subtle surface | `var(--color-muted)` | Table headers, summary blocks |
| Input surface | `var(--surface-input)` | Selects and text inputs |

### Rules

- Do not add decorative shadows to analyst panels.
- Dark mode uses the established GitHub-like slate palette from `globals.css`.
- Separate dense data with dividers and background tone, not nested cards.
- Keep cards and structural panels at an 8px radius and standard inputs and action buttons at a 6px radius.
- Selection controls may use an 8px radius so adjacent choices remain distinct. Their selected state must use a solid accent fill and contrasting text rather than elevation.

## 8. UI Terminology

UI 문구를 추가하거나 바꿀 때는 이 절의 용어를 먼저 따른다.

### General Rules

- 기존 화면, 라우트, 백엔드 로그, 테스트의 용어를 우선한다.
- 같은 기능은 페이지, 버튼, 카드 제목, 상태 문구에서 같은 명칭을 쓴다.
- 새 기능명이 필요하면 먼저 이 절에 추가하고, 같은 변경에서 UI와 테스트를 맞춘다.
- 버튼, 카드, 입력, 아이콘, 상태 표시는 기존 화면과 공통 컴포넌트/에셋을 우선 재사용한다.
- 파일 형식 설명은 도움말이나 상세 문구에만 넣고 버튼명에는 넣지 않는다.

### Existing Data Inspection

- 검사 전·검사 중·성공·실패·복구 필요 상태가 바뀌어도 카드와 검사 행의 개수는 바뀌지 않는다. 복구 동작은 실패한 기존 행의 우측 버튼을 교체해 제공하며, 결과에 따라 별도 박스나 행을 추가하지 않는다.

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Existing data review card | 기존 데이터 검토 | A standalone preflight card. Placement and behavior follow [components/inspection-block.md](./components/inspection-block.md). |
| Existing data integrity inspection action | 검사하기 | Use one right-side control: show `검사하기` before the first run, a loading state while running, and the clickable result `정상` or `사용 불가` afterward. Clicking a result runs the same inspection again. |
| Existing data clear verdict | 정상 | Use only when every page-owned inspection step on the card has passed. If an HTML save inspection reports downloadable targets, keep the overall verdict at `사용 불가` and replace that same row's action with `재다운로드`; do not add a follow-up inspection row. |
| Existing data blocked verdict | 사용 불가 | Use when a mismatch or integrity failure blocks reuse. Keep the failed step and repair action visible. On HTML save pages, a 파생 필터 with 상위 필터에 없는 원문 is also 사용 불가; do not offer 재다운로드. |
| Existing data download-required step | 다운로드 필요 | Warning state on the single HTML save inspection row while owner-mode files require `재다운로드`. Do not add a separate download row. |
| Existing data successful step state | 정상 | Use for every completed inspection step with no issue, including metadata, settings, saved files, and KIND count checks. Keep specific evidence in the step summary. |
| Existing data inspection-pending state | 대기 | Neutral default before the user clicks `검사하기`. Loading a page or changing an input must not start an integrity API. Input changes invalidate only the affected step and its dependents as defined in [components/inspection-block.md](./components/inspection-block.md). |
| Existing data inspection-complete notification | 정상 | Passive green right-dock state after a manual inspection succeeds. Do not open a dock panel automatically. |
| Page-level workflow mode switch | 세부 페이지 선택 | Shared `WorkflowModeSwitch` for choosing a numbered workflow subpage. It is not a card and has no visible group title. Its relationship to `기존 데이터 검토` follows [components/inspection-block.md](./components/inspection-block.md). |
| Apply saved metadata settings | 저장된 설정 적용 | Right-side repair action in the failed settings-comparison step, aligned with the inspection action. |
| Downloaded disclosure source data | 다운로드한 원본 데이터 | User-facing name for the downloaded page data checked before disclosure table conversion. |
| Disclosure conversion manifest | 변환 기록 | User-facing name for the manifest that records conversion summaries and output files. Do not expose `매니페스트` in guidance text. |
| Year-partitioned SQLite shard | 연도별 SQLite 파일 | User-facing name for a SQLite shard split by year. Keep `shard` as an internal implementation term only. |

### Disclosure Workspace Storage

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Per-stage disclosure storage settings | 단계별 저장 위치 | Place directly below `작업공간 디렉토리` in the right settings panel. Detail pages show only their own storage folders; external HTML shows separate save/compress folders and `공시 자동화` shows all eight storage folders. |
| Stage storage local state | 로컬 | Means the numbered stage directory under the selected workspace is used directly. |
| Invalid stage storage link | 설정 오류 | Keep `변경` and `연결 해제` available so the invalid target can be corrected or removed. Do not use the local stage as a fallback. |
| Stage storage target root | 대상 작업공간 | The selected root must contain the same numbered stage directory. Show the resolved stage directory before saving. |
| Stage storage link action | 연결 | Opens the target-workspace editor for a local stage. |
| Stage storage change action | 변경 | Opens the target-workspace editor for a linked stage. |
| Stage storage unlink action | 연결 해제 | Removes only the link file. Never imply that target data is deleted or moved. |
| Stage storage save action | 변경사항 저장 | Creates or replaces the link after validation. Disable while a workflow job is active. |

### Disclosure Automation Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Disclosure stages 1–7 orchestration workflow | 공시 자동화 | Use for the page that plans and runs the seven disclosure workflows together. Keep the seven stage labels unchanged. |
| Disclosure automation preflight result | 실행 계획 | Shows which stage entities will run, be reused, or be blocked before execution. |
| Disclosure automation detail-output inspection result | 확인됨 | Green state only after the current profile, all prerequisite inputs, expected membership, integrity checks, and recomputed outputs agree for either detail-page or continuous-run artifacts. |
| Disclosure automation detail-output inspection action | 검사 | Per-stage action placed to the right of `설정`; checks only that stage in the selected workspace. |
| Disclosure automation detail-output inspection mismatch | 확인 필요 | Amber state after inspection finds mismatched settings, incomplete inputs, missing outputs, or damaged outputs. Show the reason below the state. |
| Disclosure automation manual discovery/run action | 동기화 | Checks page 1 for every saved yearly range. If the page count changed, wait for confirmation before downloading that full range again. |
| Disclosure automation page-count conflict | 페이지 수 충돌 | Use in `알림` when a saved yearly range and KIND page 1 report different total page counts. |
| Disclosure automation page-count conflict confirmation | 전체 다시 받기 | Right-side `알림` action that confirms every page in the listed yearly ranges may be downloaded again. |
| Disclosure automation unresolved decision state | 판단 필요 | Use when a new section pattern or another configured judgment boundary requires user input. Do not silently include or exclude the affected item. |
| Disclosure automation interrupted-run continuation action | 이어서 실행 | Creates a successor run with the same revision, execution mask, and search snapshot; it does not change the original run back to running. Reuse already validated artifacts. |
| Disclosure automation review-resolution successor run | 후속 실행 | Starts a new run on the successor profile revision after a decision; do not label this as `이어서 실행`. |
| Disclosure automation continuous work range | 시작·종료 작업 선택 | Use compact checkbox-style vertical-drag controls in the first `작업표` column, showing checks only for the continuous selected range. Do not add separate endpoint icons, a task-box row, duplicate dropdowns, expose stage numbers, or allow gaps inside the range. |
| Disclosure automation settings jump action | 설정 | Use an outlined button in the unlabeled far-right action cell of `작업표`; it scrolls to the matching shared settings card. Do not place it beside the task name or add a visible `설정` column. |
| Disclosure automation inactive judgment settings | 잠긴 설정 카드 | Render only the existing card title and a lock icon when its task is outside the selected range. This is a non-interactive replacement, not a collapsible control. |
| Disclosure automation waiting for user decision | Pending | Use after upstream artifacts are not ready yet or when the workflow has stopped for a required section-pattern decision. The successor run remains `후속 실행`. |
| Disclosure automation disabled plan action | 사용 안 함 | Plan state for a task outside the selected continuous work range. |
| Disclosure automation reuse plan action | 재사용 | A validated artifact with the same input fingerprint will be reused. |
| Disclosure automation process plan action | 실행 예정 | New or stale entities will be processed. |
| Disclosure automation removal plan action | 제외 예정 | Removes entities from the next generation membership without deleting their cache. |
| Disclosure automation blocked plan action | 차단됨 | A required valid prerequisite is missing or stale and cannot be built by this run. |
| Disclosure automation audit overdue state | 재검사 지연 | A recent/cold/remote audit exceeded its configured freshness deadline; do not show the profile as complete or fresh. |
| Disclosure automation queued runtime status | 대기 중 | Runtime status for a run/stage/entity that has not started. |
| Disclosure automation running runtime status | 실행 중 | Runtime status while work is actively running. |
| Disclosure automation successful runtime status | 완료 | Runtime success only; use the separate publish state to show whether a generation became active. |
| Disclosure automation partial-error runtime status | 일부 실패 | The run completed with retained errors and did not publish its candidate generation. |
| Disclosure automation failed runtime status | 실패 | A completion invariant failed. |
| Disclosure automation cancelled runtime status | 취소됨 | The user requested cancellation; validated cache may remain. |
| Disclosure automation interrupted runtime status | 중단됨 | The process stopped before completion and can create an `이어서 실행` successor. |
| Disclosure automation pending publish state | 게시 예정 | The full enabled-stage candidate is eligible to publish after all gates pass. |
| Disclosure automation published state | 게시 완료 | The candidate generation became the active generation. |
| Disclosure automation not-published state | 게시 안 함 | A diagnostic/subset/error/review run retained cache but did not change the active generation. |

### Disclosure HTML Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| KIND egress route settings | KIND 네트워크 경로 | Right-side settings section shown only on `공시원문 외부 저장`, `공시원문 내부 저장`, and `공시 자동화`. Keep it provider-neutral. Index the fixed direct connection as route 0 and allow localhost HTTP proxy routes up to the current CPU count minus one. |
| KIND egress route add action | 경로 추가 | Adds one editable localhost HTTP proxy address. |
| KIND egress route check action | 연결 검사 | Checks the unsaved route list and reports each public IP, connection failure, and duplicate IP before saving. |
| KIND egress route save action | 변경사항 저장 | Persists the current proxy route list for later KIND work. Keep it disabled while the edited list matches the saved list. Checking does not save. |
| KIND egress route unchecked state | 검사 필요 | Header summary shown before the first check and immediately after any route is added, edited, or removed. |
| KIND egress route duplicate state | IP 중복 | Indicates that two or more configured routes resolve to the same public IP. |
| KIND egress route IP result | 공인 IP: 정상(IP) | Keep connection state and public IP in one line beneath the route. Use `공인 IP: 검사 필요`, `공인 IP: 연결 실패`, or `공인 IP: 중복(IP)` for the other states instead of a separate right-side status label. |
| External HTML download workflow | 공시원문 외부 저장 | Navigation/page workflow name. |
| Internal HTML download workflow | 공시원문 내부 저장 | Navigation/page workflow name. |
| Internal HTML section workflow | 공시원문 목차 분리 | Navigation/page workflow name. |
| Internal HTML section source load action | 소스 불러오기 | Button/action on `공시원문 목차 분리` that reads the selected HTML folder on demand. Use instead of loading large folders automatically. |
| Internal HTML section folder open action | 폴더 열기 | Button/action that opens a folder and lists individual disclosure HTML files. |
| Internal HTML selected disclosure source view | 원문 보기 | Row action that loads the selected disclosure source and its section review data. |
| Internal HTML selected disclosure split action | 목차 분리 | Button/action that splits the selected disclosure into TOC sections for review. |
| Internal HTML selected disclosure section view | 목차별 보기 | Button/action and result card that split and show the selected disclosure by TOC section. |
| Internal HTML section save action | 목차 저장 | Button/action that structurally splits every TOC range, removes only the correction section, and saves the remaining ranges as one HTML file per disclosure while preserving the source-relative path. |
| Internal HTML individual disclosure table | 개별 공시 | Table listing per-file section lists and source-open actions. |
| Internal HTML individual disclosure section count | 목차 수 | Column showing the number of sections in each listed disclosure. |
| Internal HTML problem file table | 문제 파일 | Table listing files without TOC sections and files that failed to read. |
| Disclosure HTML problem file setting | 문제 파일 표시 수 | Right-side setting for the maximum problem-file rows returned by an HTML inspection or validation error. Default to 20. |
| Disclosure HTML delete confirmation input | 확인 문구 | Labeled input shown before the destructive action. Require the exact text `확인했습니다.`. |
| Disclosure HTML delete authorization | 삭제 허가 | Checkbox shown with the confirmation input. Do not expose the destructive delete button until both safeguards are satisfied. |
| Internal HTML folder summary row | 폴더 요약 | Row box showing selected-folder file and section counts. |
| Internal HTML job status row | 작업 상태 | Row box showing the latest job/API status log. |
| Disclosure filter mode folder | 모드 | Filter identity and folder key under `03-filter`; store its definition at `<data_root>/03-filter/<mode>/filter.json`. The selector uses workspace-saved filters and never a hardcoded parser list. |
| Disclosure filter selector | 조건검색 필터 | Typeable dropdown of mode-owned `filter.json` files. Selecting an existing name immediately applies its conditions. Typing a new valid mode name and saving creates that filter. Do not add a separate name field, rename action, or manual load action on `공시내역 필터링`. Later numbered workflow pages that only choose a saved filter reuse this same dropdown; do not substitute a native `<select>`. Create, save, and delete stay on `공시내역 필터링`. |
| Disclosure top-level filter | 기본 필터 | A filter that reads stage 02 directly and owns its stage 04 and 05 raw HTML. Choose it inside `공시 조건` when creating a `조건검색 필터`. The selector lists workspace-saved filters, not a hardcoded parse-mode list. |
| Disclosure derived filter | 파생 필터 | A one-level child filter that applies additional conditions to a completed `기본 필터`. Display it as `<상위> › <자식>` when the parent is not already visible. On the derived-filter page, where `상위 필터` is shown directly above the child selector, display only the child name. Send the child `mode` and `parent_mode` separately. Choose it inside `공시 조건`. |
| Disclosure derived-filter help action | 파생 필터 설명 | Circle-help button immediately to the right of the `파생 필터` selector label. Explain that a derived filter adds conditions only to a completed parent result and supports one child level. Do not place this copy in `필드 설명`. |
| Disclosure derived-filter parent | 상위 필터 | A completed `기본 필터` selected as the input of a `파생 필터`. Do not offer another derived filter as a parent. |
| Derived filter missing parent HTML | 상위 필터에 없는 원문 | Inspection evidence when a 파생 필터 target is absent from the 상위 필터 HTML. The single existing-data inspection row is 사용 불가 and must not offer 재다운로드; complete the 상위 필터 first. |
| Disclosure filter workflow status | 작업 상태 | Persist filter state as `입력 완료`, `실행 중`, `중단됨`, `완료`, or `실패`, but do not append this changing state to the fixed mode shown in the selector. |
| Disclosure filter workflow | 공시내역 필터링 | Stage 03 sidebar item combining the `공시내역 제목 검색` and `공시내역 필터링` actions with one shared `공시 조건` box. The page opens in `공시내역 제목 검색`. |
| Disclosure filter existing-data inspection scope | 조건검색 폴더 전체 검사 | Manual inspection on stage 03 checks every mode-owned `03-filter/<mode>/filter.json` independently; it does not require a selected `조건검색 필터`. |
| Disclosure external HTML save inspection scope | 모든 모드 외부 HTML 검사 | The top inspection on `외부 HTML 저장` checks every basic and derived workspace mode independently of the selected `조건검색 필터`. Any missing, invalid, hash-mismatched, or unverified target makes the overall verdict `사용 불가`; list every mode result without adding another inspection card. |
| Disclosure external HTML redownload action | 재다운로드 | Repair action replacing `검사하기` in the single all-mode `기존 원문 데이터 검사` row whenever owner-mode downloads remain. Do not add a separate `미저장 원문 다운로드` row. Process only affected base-mode-owned files, never duplicate derived-mode work, and run the all-mode inspection again when finished. |
| Disclosure internal HTML inspection scope | 모든 모드 내부 HTML 검사 | The top inspection on `공시원문 내부 저장` checks every basic and derived workspace mode independently of the selected `조건검색 필터`, using the same aggregate verdict and mode-result structure as external HTML save. |
| KIND source HTML unavailable | KIND 원본 없음 | Use only after an internal HTML re-download fails and a direct revalidation confirms that KIND still returns no content path or invalid HTML. Keep the receipt number in the manifest and job log, exclude it from repeated download-required failures, and show its count in inspection results. |
| Disclosure internal HTML redownload action | 재다운로드 | Repair action replacing `검사하기` in the single all-mode internal HTML inspection row. Re-download only missing, invalid, hash-mismatched, or unverified owner-mode files, then retain the automatic all-mode verification result. |
| Disclosure external HTML compression repair action | 재생성 | Repair action shown in the existing compression inspection row when a base-mode compressed file fails. Rebuild only failed base-mode-owned files. Derived modes inspect the same parent-owned HTML/compressed pair and must not add duplicate repair work. |
| Disclosure external HTML compression skipped state | 압축 안 함 | Use for a mode with no saved source HTML. It is not a compression failure or repair target; mixed inspections continue to regenerate only modes that have source HTML. |
| Disclosure title search mode | 공시내역 제목 검색 | Read-only mode on stage 03; it searches the stage 02 SQLite database without creating an output file. Show the same filter level, parent, and `조건검색 필터` selectors as filtering mode. Selecting a saved filter immediately loads its conditions, while create, save, and delete actions remain available only in `공시내역 필터링`. |
| Disclosure filtering mode | 공시내역 필터링 | Recording mode on stage 03; it updates the stage 03 workflow result and transfer file. |
| Disclosure filter exclusive connector | XOR | Condition-block connector that matches when exactly one side is true. |
| Disclosure condition clear action | 지우기 | Icon button between `실행 취소` and `다시 실행` on `공시 조건`. Clears condition blocks to one empty row and records that change in the same undo history. |
| Disclosure condition field help action | 필드 설명 | Circle-help button next to `조건 블록`. Lists each filter field with a short definition and `ex)` examples. Market values stored in stage 02 are `유가증권`, `코스닥`, and `코넥스`. Badge values include `상장폐지`, `관리종목`, and `KOSPI200`. |
| Disclosure condition operators | 연산자 | Show only operators that apply to the selected field type. Date comparisons such as `<=` stay on `공시일`. Text fields keep contains/equals. `시장` and `배지` keep membership operators. |
| Disclosure title search action | 실행 | Starts the restorable background title-search job in `공시내역 제목 검색` mode. Use the same execution label as the filtering mode. |
| Disclosure title search result | 제목 검색 결과 | Lists distinct database titles and the matching disclosure count for each title. |
| Shared worker count setting | 워커 수 | Shared right-dock label for the parallel worker count on every disclosure page. Do not invent page-specific names such as `검색 worker 수` or `병렬 워커 수`. |
| Disclosure workflow stage index | 00–09 | Show the zero-padded stage number only in the disclosure sidebar. Keep page titles unnumbered. |
| HTML parse conversion settings | 변환 설정 | Box on `공시원문 변환` that keeps `모드` and `파싱 방법` as independent selectors. |
| HTML parse workspace mode selector | 모드 | Selects a workspace-saved `조건검색 필터`; send its `mode` and optional `parent_mode` independently of the parser. |
| HTML parser method selector | 파싱 방법 | Selects a server-registry parser implementation. The frontend must load this list from the parser-method API and must not enumerate parser keys. |
| HTML parse report preview | 리포트 미리보기 | Separate box below `변환 설정` that shows a few parsed report results as HTML tables for the selected mode and parsing method. |
| HTML parse warning files page open action | 현재 페이지 열기 | Button in the right-side `알림` panel on `공시원문 변환` that opens the current page of source HTML files with parse warnings. Pages contain 20 files. |
| HTML parse warning code label | 오류코드 | Label in the right-side `알림` panel on `공시원문 변환` for grouping parse warnings by stable warning code. |
| HTML parse weak warning level | 약한 에러 | Warning level label in the right-side `알림` panel on `공시원문 변환`. |
| HTML parse medium warning level | 일반 에러 | Warning level label in the right-side `알림` panel on `공시원문 변환`. |
| HTML parse strong warning level | 강한 에러 | Warning level label in the right-side `알림` panel on `공시원문 변환`. |
| HTML parse issue method filter option | 사채발행방법 | Registry-provided execution option in a separate `실행 옵션` box below `변환 설정`. |
| HTML parse rights issue method filter option | 증자방식 | Registry-provided execution option in a separate `실행 옵션` box below `변환 설정`. |
| HTML parse execution option examples action | 예시 | Row action next to an execution option candidate count that shows sample matching `acpt_no` values in `알림`. |
| HTML parse execution option example source open action | 열기 | Button in `알림` for opening one sample source HTML from an execution option candidate example. |
| Disclosure correction history workflow | 공시 정정내역 한눈에 | Stage 08 sidebar item and `/html-change-log` page title. This view reads stage 07 results and does not create an `08-*` data directory. |
| Disclosure correction history load action | 변동 불러오기 | Loads correction families and their changed fields from the selected parse result. |
| Disclosure correction history threshold settings | 변동 임계값 | Date and numeric thresholds in the right-side `설정` panel on `공시 정정내역 한눈에`. |
| Disclosure relationship graph workflow | 공시 관계 그래프 | Stage 09 sidebar item and `/disclosure-graph` page title. It saves the standard graph document under `09-disclosure-graph`. |
| Disclosure graph data card | 그래프 데이터 | Input and build controls for stage 09. |
| Disclosure graph build action | 그래프 생성 | Builds and saves the stage 09 graph document from complete stage 03/07 source pairs. |
| Disclosure graph saved-result load action | 저장 결과 불러오기 | Loads the stage 09 graph document without rebuilding it. |
| Disclosure result review group | 결과 검수 | Unnumbered disclosure sidebar group for read-only helpers that are not workflow stages. |
| Bond issuance result review | 발행내역 한눈에 | Unnumbered read-only helper for reviewing `bond_issuance` parse results. |
| External HTML save mode/button | 외부 HTML 저장 | Top mode button in 공시원문 외부 저장. |
| External HTML compression mode/button | 외부 HTML 압축 | Use for the compact JSON creation from saved external HTML. |
| Existing external HTML trust confirmation | 현재 외부 HTML 신뢰 | Explicit confirmation that externally supplied files may be used as the integrity baseline. |
| External HTML integrity baseline action | 기준 해시 생성 | Calculates and stores SHA-256 values for explicitly trusted existing external HTML files. |
| Existing internal HTML trust confirmation | 현재 내부 HTML 신뢰 | Explicit confirmation that externally supplied internal HTML files may be used as the integrity baseline. |
| Internal HTML integrity baseline action | 기준 해시 생성 | Calculates and stores SHA-256 values for explicitly trusted existing internal HTML files. |
| Source folder input mode | 폴더 입력 | Toggle label. |
| Source JSON file input mode | JSON 파일 입력 | Toggle label. |
| Output split storage | 분할저장 | Keep this spelling. |
| Align with existing metadata | 기존 메타데이터 기준으로 설정 맞추기 | Button label. |

### Utility Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Utility sidebar group | 유틸리티 | Use for the sidebar group containing `분할저장`. |
| Partition storage conversion workflow | 분할저장 구조 전환 | Use for the Utility page/card that converts between flat folders and year-split folders. |
| Price data top-level workflow | 주가데이터 | Use as the top-level menu for Quantiwise-based price data pages. Do not repeat it in page titles. |
| Quantiwise sidebar group | Quantiwise | Use as the left sidebar group under the `주가데이터` top-level workflow. |
| Price data Excel preview sidebar item | Excel 미리보기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel`. |
| Price data convert sidebar item | Parquet 변환하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/convert`. |
| Price data Parquet preview sidebar item | Parquet 미리보기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/parquet`. |
| Price data merge sidebar item | Parquet 병합하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/merge`. |
| Price data Excel preview workflow | Excel 미리보기 | Use for the `/utility/assets-excel` navigation label and page title. |
| Price data Excel convert workflow | Parquet 변환하기 | Use for the `/utility/assets-excel/convert` navigation label and page title. |
| Price data Parquet preview workflow | Parquet 미리보기 | Use for the `/utility/assets-excel/parquet` navigation label and page title. |
| Price data Parquet merge workflow | Parquet 병합하기 | Use for the `/utility/assets-excel/merge` navigation label and page title. |
| Output or saved data path | 데이터 경로 | Use instead of `저장 경로` or `저장 폴더` for reusable path inputs. |
| Source data path | 작업공간 디렉토리 | Use the same path label for every folder/file picker in the right-dock settings. Do not invent input/output/source variants. |
| Result data path | 작업공간 디렉토리 | Same as the workspace path label. Right-dock settings never distinguish input and output with different names. |
| Quantiwise Parquet grouped result table | Parquet 모아보기 | Use for the table that lists generated Parquet outputs on `Parquet 미리보기`. |
| Quantiwise merge candidate table | 병합대상 모아보기 | Use for the selectable merge-candidate table on `Parquet 병합하기`. |
| Quantiwise merge target path | 작업공간 디렉토리 | Same shared path label as every other right-dock folder picker. |
| Quantiwise merge output path | 작업공간 디렉토리 | Same shared path label as every other right-dock folder picker. |
| Quantiwise same-folder merge setting | 동일 폴더에서 작업하기 | System setting for forcing merge output work into the selected workspace directory. |
| Quantiwise cleanup merged items setting | 병합된 요소 정리하기 | System setting for moving successfully merged input Parquet files into `merged`. |
| Quantiwise duplicate recursive scan setting | 내부까지 검사 | System setting for including subfolders recursively in `중복 검사하기`; default is off. |
| Quantiwise duplicate Parquet cleanup action | 중복 검사하기 | Button/action on `Parquet 병합하기` that finds same-account Parquet files fully covered by a more complete same-account file before deletion. |
| Quantiwise conversion pre-run check | 변환 전 확인 | Use for the automatic check that scans Excel files without saving before `Quantiwise 변환`. |
| Quantiwise conversion target Excel table | 대상 파일 | Use for the selectable Excel file table on `Parquet 변환하기`. |
| Quantiwise account ID mapping | 계정-ID 매핑 | Use for the editable Sheet/account_id/account_name mapping in `Parquet 변환하기`. |

### Ontology Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Ontology real-data workspace | Graph View | Use for the production Ontology analysis page. |
| Ontology chart workspace | Chart View | Use for the production Ontology event-price chart page. |
| Ontology data status | 데이터 상태 | Source readiness panel for KIND and Quantiwise data. |
| Ontology company selector | 회사 선택 | Company selector backed by KIND SQLite shards, shown in the right settings panel. |
| Ontology stock selector | 종목 선택 | Top selector for changing the active stock in `A000000` format. |
| Ontology node graph | 공시 관계 그래프 | Obsidian-like graph-viewer canvas showing company, disclosure group, and disclosure event relationships. |
| Ontology node search | 노드 검색 | Search input for nodes inside the Ontology node graph. |
| Ontology graph unpin action | 핀 해제 | Clears pinned nodes in the Ontology node graph. |
| Ontology graph hidden-state reset action | 숨김 초기화 | Keep one action in the top graph toolbar; do not duplicate it in the selected-item detail panel. |
| Ontology event-price chart | 주가-공시 차트 | Plot combining Quantiwise price candles and KIND disclosure markers. |
| Ontology chart condition panel | 공시 조건 | Top condition box on Chart View that manages company search, `resources/KIND` disclosure category selection, and chart display buttons. |
| Ontology chart company section | 회사명 | Section label for company-name search in the Chart View condition panel. |
| Ontology chart disclosure section | 공시내역 | Section label for KIND disclosure category selection in the Chart View condition panel. |
| Ontology chart disclosure group selector | 공시 선택 | Selector label for choosing `전체` or one category folder under `resources/KIND`. |
| Ontology event timeline | 공시 타임라인 | List of visible disclosures for the selected company and period. |
| Ontology disclosure analysis | 공시 분석 | Event analysis workspace for triple-barrier and related disclosure tests. |
| Ontology triple barrier execution action | Triple Barrier 실행 | Button/action on `공시 분석` that calculates and stores Triple Barrier labels. |
| Ontology triple barrier execution company selector | 실행 종목 선택 | Stock search box used only for the Triple Barrier execution flow. |
| Ontology triple barrier execution company search action | 실행 대상 검색 | Button that searches stocks for the execution flow. |
| Ontology triple barrier result company selector | 결과 종목 선택 | Stock search box used only for saved Triple Barrier result lookup. |
| Ontology triple barrier result company search action | 저장 결과 검색 | Button that searches stocks for persisted-result review. |
| Ontology triple barrier selected result lookup action | 선택 종목 결과 조회 | Button that reloads persisted results for the selected result company. |
| Ontology triple barrier event basis | 이벤트 기준일 | Selector for using disclosure date or disclosure timestamp as event time. |
| Ontology triple barrier price basis | 가격 기준 | Selector for close-based or intraday high/low-based barrier checks. |
| Ontology triple barrier result table | 결과 테이블 | Stored Triple Barrier label result table on `공시 분석`. |
| Ontology triple barrier run mode | 실행 설정 | Mode/menu label for configuring and running Triple Barrier on `공시 분석`. |
| Ontology triple barrier results mode | 저장 결과 | Mode/menu label for reviewing stored Triple Barrier rows on `공시 분석`. |
| Ontology triple barrier disclosure group selector | 공시 선택 | Selector label for choosing `전체` or one `resources/KIND` category before Triple Barrier execution. |
| Ontology triple barrier selected event table | 검사 대상 이벤트 | Selectable event list scoped by stock and disclosure category on `공시 분석`. |
| Ontology triple barrier result summary | 저장 결과 요약 | Summary row for stored Triple Barrier result counts and latest parameter hash. |
| Ontology chart frequency selector | 일봉/3일봉/5일봉/7일봉/20일봉/월봉 | Chart candle aggregation selector below the chart action buttons. |
| Ontology chart type selector | 캔들/종가선 | Chart type selector for OHLC candles or close-only line plotting. |
| Ontology final report marker | 최종보고서 | Y/N field for whether a disclosure is the latest report in a correction chain. |
| Ontology full date range | 전체 기간 | Default date range for Graph View chart and disclosure analysis. |
| Ontology chart fullscreen action | 전체화면 | Opens the chart in an app-level fullscreen overlay. |
| Ontology chart exit fullscreen action | 전체화면 닫기 | Closes the chart fullscreen overlay. |
| Ontology chart zoom sensitivity | 확대/축소 민감도 | Chart interaction setting in the right settings panel. |
| Ontology chart marker style section | 공시 마커 스타일 | Compact section in the Chart View condition panel for editing disclosure marker appearance. |
| Ontology chart marker style target | 스타일 대상 | Selector for choosing `전체` or one disclosure group before editing marker style controls. |
| Ontology chart marker placement setting | 공시 마커 위치 | Settings control for where disclosure markers render on the price chart. |
| Ontology chart marker shape setting | 공시 마커 모양 | Settings control for disclosure marker symbol shape on the price chart. |
| Ontology chart marker color setting | 색상 | Color control for the selected disclosure marker style target. |
| Ontology chart marker size setting | 크기 | Size control for the selected disclosure marker style target. |
| Ontology chart marker line width setting | 선 두께 | Stroke-width control for the selected disclosure marker style target. |

### Right Dock Panels

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Activity panel | 실행 현황 | Use for the right dock activity button and panel title across pages. |
| Notification panel | 알림 | Use for errors, warnings, confirmations, user action required, or passive completion feedback. New content changes the dock icon tone but never opens the panel automatically. |
| Notification clear action | 지우기 | Button in the right-side `알림` panel that clears the currently accumulated notification display. |
| Settings panel | 설정 | Use as the generic right dock settings title unless a page-specific settings title is already established. |
| Shared worker count setting | 워커 수 | Shared right-dock worker-count label. Same wording on download, table, filter, HTML, and automation pages. |
| KIND egress route progress | KIND 네트워크 경로 | Reports the direct route and configured proxy routes in `실행 현황`. Each route has its own HTTP sessions, request spacing, and per-minute limit. |
| Shared request timeout setting | 타임아웃 (초) | Shared right-dock timeout label. |
| Shared request interval setting | 요청 간격 (초) | Shared right-dock wait/interval label. Do not use `대기 시간 (초)` or `요청 timeout(초)`. |
| Shared progress interval setting | 진행 확인 간격 (건) | Shared right-dock progress-interval label. Do not use `진행 표시 간격`. |
| Shared max-item setting | 최대 처리 건수 | Shared right-dock limit label. Do not use `최대 반환`. |
| Shared page-size setting | 페이지 크기 | Shared right-dock KIND page-size label. Do not use `페이지당 공시 수`. |
| Download parallel strategy setting | 병렬 처리 방식 | Selects whether workers are distributed across yearly ranges or pages within one year. |
| Parallel yearly ranges option | 연도별 병렬 | Runs multiple yearly download folders concurrently. Shown as a right-side inspector select under `병렬 처리 방식`. |
| Parallel pages within one year option | 한 연도 내 병렬 | Runs yearly folders in sequence and downloads pages within the active year concurrently. Shown as a right-side inspector select under `병렬 처리 방식`. |
| Background job retention setting | 작업 기록 보관 시간 (분) | Retains terminal in-memory job status for the configured number of minutes. It never removes saved files or workflow metadata. |
| Active job elapsed time | 작업 경과 | Show server-reported elapsed time while a right-dock background job is queued or running. |
| HTML download throughput | 다운로드 속도 | Show `download/min` from actual network downloads completed during the latest 10 seconds, multiplied by six. Exclude reused or skipped files. |
| Active job progress freshness | 진행 확인 | Pair `상태 조회 정상` with either the age of the latest log or `새 로그 N초째 없음` after 10 seconds. This reports observed API/log freshness and does not claim that silent work has stopped. |
| Disclosure separate output directory setting | (not shown in UI) | Code/config only. The right-dock settings panel never exposes a separate save-directory toggle. Jobs use the canonical stage directory under the workspace unless a payload or saved setting overrides the path. |
| Disclosure workspace root path | 작업공간 디렉토리 | Shared root directory shown on every disclosure detail page. All canonical stage paths are resolved below this directory. |

Right dock panels align exactly with the workflow content at the top of the page. On desktop, they begin following only after scrolling past a `24px` viewport inset, using the shared bounded spring motion; reduced-motion mode moves directly to the same bounded position. Do not use a sticky top offset, because it shifts the dock out of alignment before scrolling begins.

Right dock buttons and notices use only three semantic tones: green for successful completion; amber for running work, warnings, or required decisions; red for errors. An active `실행 현황` or `알림` button always uses one of these tones, including a running job. There is no gray notification badge. Inactive controls and `알림 없음` keep the default control styling. Opening a panel keeps its semantic tone only while that state is active.
