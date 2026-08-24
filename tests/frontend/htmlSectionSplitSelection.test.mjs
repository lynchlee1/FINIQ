import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
test("HTML section save runs automatically without TOC pattern decisions", async () => {
  const pageSource = await readFile(pagePath, "utf8");

  assert.match(pageSource, /\/api\/disclosures\/html\/sections\/save\/start/);
  assert.match(pageSource, /workers: parseOptionalNumber\(workers\)/);
  assert.doesNotMatch(pageSource, /section_save_rules|selectedPatternTocIds|patternsWithoutSelection/);
  assert.doesNotMatch(pageSource, /sections\/kinds\/start|HtmlSectionPatternCard/);
  assert.doesNotMatch(pageSource, /Pending|저장할 목차를 선택/);
});
