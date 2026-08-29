import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
const resultsPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx";
test("HTML section save runs automatically without TOC pattern decisions", async () => {
  const pageSource = await readFile(pagePath, "utf8");

  assert.match(pageSource, /\/api\/disclosures\/html\/sections\/save\/start/);
  assert.match(pageSource, /workers: parseOptionalNumber\(workers\)/);
  assert.doesNotMatch(pageSource, /section_save_rules|selectedPatternTocIds|patternsWithoutSelection/);
  assert.doesNotMatch(pageSource, /sections\/kinds\/start|HtmlSectionPatternCard/);
  assert.doesNotMatch(pageSource, /Pending|저장할 목차를 선택/);
});

test("HTML section preview preserves and indents structural TOC hierarchy", async () => {
  const source = await readFile(resultsPath, "utf8");

  assert.match(source, /kind\?: "preamble" \| "cover" \| "part" \| "section" \| "document"/);
  assert.match(source, /parent_toc_id\?: string \| null/);
  assert.match(source, /is_toc\?: boolean/);
  assert.match(source, /Math\.max\(0, section\.level \|\| 0\) \* 16/);
  assert.match(source, /item\.toc_count \|\| 0/);
  assert.match(source, /splitResult\.toc_count \|\| 0/);
  assert.match(source, /item\.source_unavailable/);
  assert.match(source, /KIND 원본 없음/);
});

test("HTML section save shows every structure type from the completed execution", async () => {
  const pageSource = await readFile(pagePath, "utf8");
  const resultsSource = await readFile(resultsPath, "utf8");

  assert.match(pageSource, /data\?\.format === "finiq_disclosure_html_section_save_v2"/);
  assert.match(pageSource, /setSectionPatterns\(data\.section_patterns \|\| \[\]\)/);
  assert.match(pageSource, /<HtmlSectionStructureTypes sectionPatterns=\{sectionPatterns\} \/>/);
  assert.match(resultsSource, /title="목차 구조 종류"/);
  assert.match(resultsSource, /sectionPatterns\.map\(\(pattern, patternIndex\) =>/);
  assert.match(resultsSource, /pattern\.sections\.map\(\(section\) =>/);
  assert.match(resultsSource, /sectionKindLabel\(section\)/);
  assert.match(resultsSource, /section\.will_remove/);
  assert.match(resultsSource, /제거 예정/);
  assert.match(resultsSource, /Math\.max\(0, section\.level - 1\) \* 20/);
  assert.match(resultsSource, /pattern\.sections\.filter\(\(section\) => section\.is_toc\)\.length/);
  assert.match(resultsSource, /전체 구간 수/);
  assert.match(resultsSource, /pattern\.section_count/);
  assert.match(resultsSource, /pattern\.count/);
  assert.doesNotMatch(resultsSource, />\{pattern\.signature\}</);
});

test("source-unavailable documents never request section splitting", async () => {
  const pageSource = await readFile(pagePath, "utf8");
  const resultsSource = await readFile(resultsPath, "utf8");

  assert.match(pageSource, /if \(!document\.source_unavailable\) \{\s*void splitDocument\(document\)/);
  assert.match(
    resultsSource,
    /disabled=\{!selectedDocument \|\| Boolean\(selectedDocument\.source_unavailable\)\}/,
  );
});

test("HTML section mode changes refresh the mode-owned input and output paths", async () => {
  const pageSource = await readFile(pagePath, "utf8");
  const handler = pageSource.slice(
    pageSource.indexOf("const handleFilterChange"),
    pageSource.indexOf("const handleOutputDirectoryChange"),
  );

  assert.match(handler, /await saveSetting\("html_parse_mode", preset\.mode\)/);
  assert.match(handler, /setInputDirectory\(settings\.internal_html_output_directory \|\| ""\)/);
  assert.match(handler, /setOutputDirectory\(settings\.html_section_split_output_directory \|\| ""\)/);
});
