import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";
const inspectionPanelPath = "frontend/finiq_GUI/apps/market-desk/src/components/data-integrity/DataIntegrityInspectionPanel.tsx";
const inspectionHookPath = "frontend/finiq_GUI/apps/market-desk/src/hooks/useDataIntegrityInspection.ts";
const actionDockPath = "frontend/finiq_GUI/packages/web-app/src/components/ui/ActionDock.tsx";
const actionDockFollowPath = "frontend/finiq_GUI/packages/web-app/src/components/ui/useActionDockFollow.ts";
const globalsPath = "frontend/finiq_GUI/apps/market-desk/src/app/globals.css";

test("download review is separate from search conditions and actionable steps own right-side actions", async () => {
  const [source, panel] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionPanelPath, "utf8"),
  ]);
  const searchCardStart = source.indexOf("<DisclosureSearchConditionCard");
  const reviewCardStart = source.indexOf("기존 데이터 검토");
  const searchCardClose = source.indexOf("          />", searchCardStart);

  assert.ok(searchCardStart >= 0);
  assert.ok(searchCardClose > searchCardStart);
  assert.ok(reviewCardStart > searchCardClose);
  assert.doesNotMatch(source.slice(searchCardStart, searchCardClose), /DataIntegrityInspectionPanel/);
  assert.match(source, /<CardTitle[^>]*>[\s\S]*기존 데이터 검토/);
  const settingsStep = source.slice(source.indexOf('key: "settings"'), source.indexOf('key: "files"'));
  assert.match(settingsStep, /action: !filtersMatch && savedFilters && filterDifferences\.length > 0 \? \{[\s\S]*label: "저장된 설정 적용"/);
  assert.doesNotMatch(settingsStep, /<Button\b/);
  assert.match(source, /key: "files"[\s\S]{0,3500}label: isCurrentInspectionRunning \? "검사 중\.\.\." : "검사하기"/);
  assert.ok(source.indexOf("label: isCurrentInspectionRunning") < source.indexOf('key: "kind-count"'));
  assert.match(panel, /\{step\.action \? \([\s\S]{0,500}step\.action\.label/);
  assert.doesNotMatch(source, /업데이트 기간 적용/);
  assert.doesNotMatch(source, /폴더 검사하기/);
  const executionCard = source.slice(
    source.indexOf('<CardTitle className="dark:text-white">작업 실행</CardTitle>'),
    source.indexOf("        </section>", source.indexOf('<CardTitle className="dark:text-white">작업 실행</CardTitle>')),
  );
  assert.match(executionCard, /md:grid-cols-3/);
  assert.equal(executionCard.match(/<Button\b/g)?.length, 3);
  assert.match(executionCard, />\s*미리보기\s*<\/Button>/);
  assert.match(executionCard, /onClick=\{handleRun\}[\s\S]*?\n\s+실행\s*\n\s+<\/Button>/);
  assert.match(executionCard, /\{UI_TEXT\.actions\.cancelJob\}/);
  assert.doesNotMatch(executionCard, /검사하기|저장된 설정 적용|삭제 예정 파일/);
});

test("shared integrity panel presents a verdict, ordered steps and one success label", async () => {
  const [source, panel] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionPanelPath, "utf8"),
  ]);

  assert.match(panel, /export type DataIntegrityInspectionStepStatus = "complete" \| "failed" \| "ready" \| "waiting" \| "running"/);
  assert.ok(panel.indexOf("verdict.label") < panel.indexOf("<ol className="));
  assert.match(panel, /\{step\.status === "failed" && step\.detail && \(/);
  assert.doesNotMatch(panel, /\{step\.detail && \(/);
  assert.match(panel, /step\.status === "waiting" \|\| step\.status === "ready" \? index \+ 1/);
  for (const label of ["메타데이터 읽기", "현재 설정과 비교", "저장 파일 구성 검사", "KIND 건수 비교"]) {
    assert.match(source, new RegExp(label));
  }
  assert.match(source, /const EXISTING_DATA_SUCCESS_LABEL = "정상"/);
  assert.equal(source.match(/EXISTING_DATA_SUCCESS_LABEL/g)?.length, 9);
  assert.doesNotMatch(source, /"검증 완료"|"메타데이터 확인됨"|filtersMatch \? "일치"|: "통과"/);
  assert.match(source, /filterDifferences\.map/);
  assert.match(source, /저장된 설정 적용/);
  assert.match(source, /staleRanges\.map/);
});

test("shared integrity hierarchy stays aligned with the surrounding product UI", async () => {
  const [source, panel] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionPanelPath, "utf8"),
  ]);

  assert.match(panel, /text-\[16px\][^\n]*\{verdict\.title\}/);
  assert.match(panel, /text-\[15px\][^\n]*\{step\.title\}/);
  assert.match(panel, /text-\[13px\][^\n]*\{step\.summary\}/);
  assert.match(source, /CardTitle className="[^"]*text-\[16px\]/);
  assert.doesNotMatch(panel, /text-\[18px\]/);
});

test("shared integrity step statuses and action use the same control size", async () => {
  const panel = await readFile(inspectionPanelPath, "utf8");

  assert.match(panel, /const stepControlClassName = "h-8 w-28 shrink-0 self-start justify-center whitespace-nowrap"/);
  assert.equal(panel.match(/\$\{stepControlClassName\}/g)?.length, 2);
});

test("shared inspection state ignores stale requests and full verification blocks execution", async () => {
  const [source, hook] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionHookPath, "utf8"),
  ]);

  assert.match(source, /useDataIntegrityInspection<DownloadExistingPayload, DownloadExistingResponse>/);
  assert.match(hook, /setIsChecking\(true\);\s*setError\(null\);/);
  assert.match(hook, /setError\(message\);\s*onErrorRef\.current\?\.\(message\);/);
  assert.match(hook, /requestRef\.current\.id !== requestId \|\| requestRef\.current\.key !== requestKey/);
  assert.match(source, /inspect: detectExistingDownload/);
  assert.match(source, /const hasVerificationFailure = !verified \|\|/);
  assert.match(source, /if \(hasInspectionFailure\)/);
  assert.match(source, /const completedInspection = activeInspectionRef\.current/);
  assert.match(source, /completedInspection\.jobId !== jobId/);
  assert.match(source, /const completedPayload = completedInspection\.payload/);
  assert.match(source, /const verified = data\.existing_downloads as DownloadExistingResponse/);
  assert.match(source, /acceptExistingInspectionResult\(verified\)/);
  assert.doesNotMatch(source, /await checkExistingDownload\(existingPayloadFromDownloadPayload\(completedPayload\)\)/);
  assert.match(source, /if \(verified\) \{\s*setLastInspectedExistingKey\(completedInspectionKey\);/);
  assert.match(source, /clearActiveInspection\(completedInspection\)/);
  assert.match(source, /if \(existingMetadataError\) \{\s*throw new Error\(existingMetadataError\);/);
  assert.match(source, /result\?\.dry_run === true[\s\S]{0,180}result\.deletion_candidates/);
  assert.match(source, /const mismatchedFilterRanges = existingData\?\.ranges\?\.filter/);
  assert.match(source, /mismatchedFilterRanges\.length === 0 && areFiltersMatching/);
  assert.match(source, /mismatchedFilterRanges\.map/);
  assert.doesNotMatch(hook, /catch \{[\s\S]{0,300}setResult\(null\);/);
});

test("download colored status surfaces use contrast text tokens", async () => {
  const source = await readFile(inspectionPanelPath, "utf8");
  const globals = await readFile(globalsPath, "utf8");

  for (const token of ["--tv-up-text", "--tv-down-text", "--tv-warning-text"]) {
    assert.match(globals, new RegExp(`${token}: #[0-9a-fA-F]{6};`));
  }

  assert.doesNotMatch(source, /bg-\[var\(--tv-(?:up|down|warning)-soft\)\][^"\n]*text-\[var\(--tv-(?:up|down|warning)\)\]/);
  const verdictMappings = {
    success: "--tv-up-text",
    warning: "--tv-warning-text",
    error: "--tv-down-text",
    neutral: "--tv-text",
  };
  const stepMappings = {
    complete: "--tv-up-text",
    failed: "--tv-down-text",
    ready: "--tv-warning-text",
    waiting: "--tv-muted",
    running: "--tv-accent",
  };
  for (const [state, token] of Object.entries(verdictMappings)) {
    assert.match(source, new RegExp(`${state}: "[^"\\n]*text-\\[var\\(${token}\\)\\]"`));
  }
  for (const [state, token] of Object.entries(stepMappings)) {
    assert.match(source, new RegExp(`${state}: "[^"\\n]*text-\\[var\\(${token}\\)\\]"`));
  }
});

test("manual inspection opens the activity panel and keeps progress visible", async () => {
  const [source, globals, sharedDock, dockFollow] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(globalsPath, "utf8"),
    readFile(actionDockPath, "utf8"),
    readFile(actionDockFollowPath, "utf8"),
  ]);
  const inspectHandler = source.slice(source.indexOf("const handleInspectFolder"), source.indexOf("const handleRun"));

  assert.match(inspectHandler, /setDownloadPanelOpen\(true\)/);
  assert.doesNotMatch(inspectHandler, /setNotificationPanelOpen\(true\)/);
  assert.match(source, /\} else \{\s*clearActiveInspection\(completedInspection\);\s*setNotificationPanelOpen\(false\);\s*setDownloadPanelOpen\(true\);/);
  assert.match(source, /hasSuccessfulInspectionNotification[\s\S]{0,500}tv-up/);
  assert.match(source, /hasSuccessfulInspectionNotification = [\s\S]{0,350}&& filtersMatch/);
  assert.match(source, /hasSuccessfulInspectionNotification && \([\s\S]{0,350}\{EXISTING_DATA_SUCCESS_LABEL\}/);
  assert.match(source, /const hasInspectionFailure = candidateCount > 0 \|\| hasVerificationFailure;/);
  assert.match(source, /setIsErrorStatus\(hasInspectionFailure\)/);
  assert.match(source, /failed \? "사용 불가" : deleted \? "파일 삭제 완료" : EXISTING_DATA_SUCCESS_LABEL/);
  assert.match(source, /hasWarningNotification[\s\S]{0,500}tv-warning/);
  assert.match(source, /const actionDockRef = useActionDockFollow<HTMLDivElement>\(\)/);
  assert.match(source, /<div ref=\{actionDockRef\} className="action-dock-root/);
  assert.doesNotMatch(source, /md:sticky|md:top-\[/);
  assert.match(sharedDock, /const dockRef = useActionDockFollow<HTMLDivElement>\(\)/);
  assert.match(sharedDock, /<div ref=\{dockRef\} className="action-dock-root/);
  assert.match(globals, /\.action-dock-host > \.action-dock-root \{[\s\S]{0,300}position: relative;[\s\S]{0,100}top: auto;/);
  assert.match(dockFollow, /Math\.min\(maxTravel, Math\.max\(0, VIEWPORT_INSET - hostTop\)\)/);
  assert.match(dockFollow, /translate3d\(0, \$\{current\}px, 0\)/);
  assert.match(dockFollow, /prefers-reduced-motion: reduce/);
  assert.match(dockFollow, /const \[dock, setDock\] = useState<T \| null>\(null\)/);
  assert.match(dockFollow, /useCallback\(\(node: T \| null\) => setDock\(node\), \[\]\)/);
  assert.match(dockFollow, /window\.requestAnimationFrame\(animate\)/);
  assert.match(dockFollow, /window\.removeEventListener\("scroll", updateTarget\)/);
});
