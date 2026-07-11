import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-automation/page.tsx";
const navigationPath = "frontend/finiq_GUI/apps/market-desk/src/config/navigation.ts";
const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";
const sectionResultsPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx";

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
  assert.match(page, /changeRangeStart/);
  assert.match(page, /changeRangeEnd/);
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
