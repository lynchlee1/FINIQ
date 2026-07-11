import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-automation/page.tsx";
const navigationPath = "frontend/finiq_GUI/apps/market-desk/src/config/navigation.ts";
const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";
const sectionResultsPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx";
const rangeSelectorPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureWorkflowRangeSelector.tsx";
const lockedCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureLockedSettingsCard.tsx";
const sectionPatternCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/HtmlSectionPatternCard.tsx";

test("disclosure automation is additive and keeps all seven detail routes", async () => {
  const [page, navigation] = await Promise.all([
    readFile(pagePath, "utf8"),
    readFile(navigationPath, "utf8"),
  ]);

  assert.match(navigation, /basePath: "\/disclosure-automation"/);
  assert.match(navigation, /label: "공시 자동화"/);
  for (const route of [
    "/download",
    "/table",
    "/filter",
    "/html-download",
    "/html-content-download",
    "/html-section-split",
    "/html-parse",
  ]) {
    assert.match(navigation, new RegExp(`href: "${route}"`));
    assert.match(page, new RegExp(`href: "${route}"`));
  }
});

test("automation page uses a continuous work range and in-page settings shortcuts", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.match(page, /DisclosureWorkflowRangeSelector/);
  assert.match(page, /onRangeChange=\{changeRange\}/);
  assert.match(page, /scrollIntoView/);
  assert.match(page, /바로가기/);
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
});

test("automation range is selected directly by dragging task boxes", async () => {
  const selector = await readFile(rangeSelectorPath, "utf8");

  assert.match(selector, /onPointerDown=\{handlePointerDown\}/);
  assert.match(selector, /onPointerMove/);
  assert.match(selector, /setPointerCapture/);
  assert.match(selector, /data-workflow-task-value/);
  assert.match(selector, /onRangeChange\(Math\.min\(anchor, value\), Math\.max\(anchor, value\)\)/);
  assert.doesNotMatch(selector, /SelectTrigger|SelectContent|onStartChange|onEndChange/);
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
  assert.match(sectionPatternCard, /Pending/);
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
