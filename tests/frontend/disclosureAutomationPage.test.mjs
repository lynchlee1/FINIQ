import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-automation/page.tsx";
const navigationPath = "frontend/finiq_GUI/apps/market-desk/src/config/navigation.ts";
const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";
const sectionResultsPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx";
const lockedCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureLockedSettingsCard.tsx";
const sectionPatternCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/HtmlSectionPatternCard.tsx";

test("disclosure automation navigation keeps all seven detail routes", async () => {
  const navigation = await readFile(navigationPath, "utf8");

  assert.match(navigation, /basePath: "\/disclosure-automation"/);
  assert.match(navigation, /label: "공시 자동화"/);
  for (const route of [
    "/download",
    "/table",
    "/filter",
    "/external-html-download",
    "/internal-html-download",
    "/html-section-split",
    "/html-parse",
  ]) {
    assert.match(navigation, new RegExp(`href: "${route}"`));
  }
});

test("automation page uses a continuous work range and in-page settings actions", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.doesNotMatch(page, /DisclosureWorkflowRangeSelector/);
  assert.match(page, /data-workflow-task-value=\{stage\.number\}/);
  assert.match(page, /scrollIntoView/);
  assert.match(page, /설정/);
  assert.match(page, /실행 계획/);
  assert.match(page, /DisclosureConditionFilterCard/);
  assert.match(page, /동기화/);
  assert.match(page, /이어서 실행/);
  assert.match(page, /후속 실행/);
  assert.match(page, /needs_review/);
  assert.match(page, /STAGES\.map\(\(stage\) => \[stage\.key, true\]\)/);
  assert.doesNotMatch(page, /\[stage\.key, executionMask\.includes\(stage\.number\)\]/);
  assert.doesNotMatch(page, /1·3·6|1–7|01-list부터|07-converted|Stage 1|Stage 6/);
  assert.doesNotMatch(page, /<th[^>]*>사용<\/th>|<th[^>]*>이번 실행<\/th>|<th[^>]*>설정<\/th>/);
  assert.doesNotMatch(page, /\{stage\.number\}<\/span>/);
  assert.match(page, /<option value="shareholder_meeting">shareholder_meeting<\/option>/);
});

test("automation range is selected directly by dragging task-table controls", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.match(page, /onPointerDown=\{handleRangePointerDown\}/);
  assert.match(page, /onPointerMove=\{handleRangePointerMove\}/);
  assert.match(page, /setPointerCapture/);
  assert.match(page, /data-workflow-task-value/);
  assert.match(page, /changeRange\(Math\.min\(anchor, value\), Math\.max\(anchor, value\)\)/);
  assert.match(page, /aria-pressed=\{inRange\}/);
  assert.doesNotMatch(page, /SelectTrigger|SelectContent|onStartChange|onEndChange/);
});

test("automation rejects unreadable or unsupported stored profiles", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.match(page, /format: typeof PROFILE_FORMAT/);
  assert.match(page, /stored\.format !== PROFILE_FORMAT/);
  assert.match(page, /throw new Error\(`브라우저 저장값을 읽지 못했습니다:/);
  assert.match(page, /if \(initializationError\) throw initializationError/);
  assert.doesNotMatch(page, /legacySelection|steps\?:|executionMask\?:/);
});

test("automation task table uses standard card spacing and a far-right outlined settings action", async () => {
  const page = await readFile(pagePath, "utf8");
  const tableStart = page.indexOf('<CardTitle className="text-[var(--tv-text)]">작업표</CardTitle>');
  const tableEnd = page.indexOf('<div ref={searchSettingsRef}', tableStart);
  const taskTable = page.slice(tableStart, tableEnd);

  assert.ok(tableStart >= 0 && tableEnd > tableStart);
  assert.match(taskTable, /<CardContent className="space-y-6">/);
  assert.match(taskTable, /overflow-x-auto rounded-md border border-\[color:var\(--tv-border\)\]/);
  assert.match(taskTable, /min-w-\[920px\]/);
  assert.match(taskTable, /<span className="text-sm font-medium">\{stage\.label\}<\/span>/);
  assert.match(taskTable, /className=\{`flex h-4 w-4/);
  assert.match(taskTable, /\{inRange \? <Check className="h-2\.5 w-2\.5"/);
  assert.match(taskTable, /<td className="px-5 py-2 align-middle">/);
  assert.match(taskTable, /className="h-8 border-\[color:var\(--tv-border\)\]/);
  assert.doesNotMatch(taskTable, /<Link href=\{stage\.href\}|<MoveVertical|<GripVertical|<Flag|isRangeStart \? <Play/);
  assert.match(taskTable, /<th className="w-32[^>]*><span className="sr-only">설정<\/span><\/th>/);
  assert.match(taskTable, /<div className="flex justify-end gap-2">[\s\S]*?variant="outline"[\s\S]*?설정[\s\S]*?검사/);
  assert.ok(taskTable.indexOf("formatCompletedAt") < taskTable.indexOf('<div className="flex justify-end gap-2">'));
  assert.doesNotMatch(taskTable, /variant="ghost"[\s\S]{0,220}설정/);
});

test("inactive judgment settings render locked summary cards and section review can wait", async () => {
  const [page, lockedCard, sectionPatternCard] = await Promise.all([
    readFile(pagePath, "utf8"),
    readFile(lockedCardPath, "utf8"),
    readFile(sectionPatternCardPath, "utf8"),
  ]);

  assert.match(page, /searchSettingsSelected \? <>/);
  assert.match(page, /filterSettingsSelected \? <DisclosureConditionFilterCard/);
  assert.match(page, /sectionSettingsSelected \|\| reviewPatterns\.length/);
  assert.match(page, /DisclosureLockedSettingsCard title="검색 조건"/);
  assert.match(page, /DisclosureLockedSettingsCard title="공시 종류"/);
  assert.match(page, /pending=\{!runResult \|\| !!activeJobId \|\| !!reviewPatterns\.length\}/);
  assert.match(lockedCard, /Lock/);
  assert.match(lockedCard, /min-h-8/);
  assert.doesNotMatch(lockedCard, /min-h-14/);
  assert.match(sectionPatternCard, /Pending/);
});

test("download page-count conflicts require confirmation in the notification panel", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.match(page, /workflow_status: "completed" \| "needs_download_confirmation" \| "needs_review"/);
  assert.match(page, /download_confirmation: confirmedDownload/);
  assert.match(page, /setDownloadConflicts\(conflicts\)/);
  assert.match(page, /notificationDismissible=\{!downloadConflicts\.length\}/);
  assert.match(page, /저장 \{conflict\.saved_pages \?\? "확인 불가"\}페이지 · KIND \{conflict\.kind_pages \?\? "확인 불가"\}페이지/);
  assert.match(page, /전체 다시 받기/);
  assert.match(page, /startRun\("sync", sectionRules, downloadConfirmation\)/);
});

test("automation and detail pages share the same judgment setting components", async () => {
  const [page, downloadPage, sectionResults] = await Promise.all([
    readFile(pagePath, "utf8"),
    readFile(downloadPagePath, "utf8"),
    readFile(sectionResultsPath, "utf8"),
  ]);

  for (const component of ["DisclosureSearchConditionCard", "DisclosureTypeSelectionCard"]) {
    assert.match(page, new RegExp(component));
    assert.match(downloadPage, new RegExp(component));
  }
  assert.match(page, /HtmlSectionPatternCard/);
  assert.match(sectionResults, /HtmlSectionPatternCard/);
});

test("automation page inspects detail-page outputs and shows confirmed plans", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.match(page, /\/api\/disclosure-workflows\/inspect/);
  assert.match(page, /\.\.\.buildProfile\("resume"\),\s*stage,/);
  assert.match(page, /onClick=\{\(\) => void inspectStage\(stage\.number\)\}/);
  assert.match(page, /disabled=\{!!activeJobId \|\| inspectingStage !== null\}[\s\S]{0,80}>\s*검사/);
  assert.doesNotMatch(page, /inspectingStage === stage\.number \? <Loader2/);
  assert.match(page, /const stageInspection = inspectionForStage\(stage\.number\)/);
  assert.match(page, /action === "confirmed"\) return "확인됨"/);
  assert.match(page, /action === "mismatch"\) return "확인 필요"/);
  assert.match(page, /action === "reuse" \|\| action === "confirmed"/);
  assert.match(page, /stageInspection\?\.reason \|\| stagePlan\?\.reason/);
  assert.match(page, /companyName,[\s\S]*conditions,[\s\S]*disclosureTypeGroups,[\s\S]*sectionRules/);
  assert.equal(page.match(/\/api\/disclosure-workflows\/inspect/g)?.length, 1);
});
