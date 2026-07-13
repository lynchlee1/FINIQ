import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = "frontend/finiq_GUI/apps/market-desk/src";

test("change matrix uses only backend-declared values", async () => {
  const source = await readFile(`${root}/utils/matrixUtils.ts`, "utf8");

  assert.match(source, /Array\.isArray\(family\?\.changed_field_names\)/);
  assert.doesNotMatch(source, /matrix\[f\]\[vIdx - 1\]/);
  assert.doesNotMatch(source, /firstIdx/);
});

test("chart and backtest invalid values are not converted to zero", async () => {
  const [chartSource, backtestSource] = await Promise.all([
    readFile(`${root}/lib/charts.ts`, "utf8"),
    readFile(`${root}/lib/disclosureBacktests.ts`, "utf8"),
  ]);

  assert.match(chartSource, /function finiteDataNumber/);
  assert.match(chartSource, /throw new TypeError\(`Chart \$\{field\} must be a finite number`\)/);
  assert.doesNotMatch(chartSource, /toNumber\(item\.value, 0\)/);
  assert.match(backtestSource, /returnPct: null/);
  assert.doesNotMatch(backtestSource, /returnPct: 0/);
});

test("search and summary selections do not jump to the first result", async () => {
  const paths = [
    "app/graph/OntologyGraphWorkspace.tsx",
    "app/graph/chart/OntologyChartWorkspace.tsx",
    "app/graph/analysis/DisclosureAnalysisWorkspace.tsx",
    "app/html-bond-summary/page.tsx",
  ];
  const sources = await Promise.all(paths.map((path) => readFile(`${root}/${path}`, "utf8")));

  for (const source of sources) {
    assert.doesNotMatch(source, /data\.companies\[0\]/);
    assert.doesNotMatch(source, /filteredRecords\[0\]/);
  }
});

test("company graph failure does not replace the result with an empty graph", async () => {
  const source = await readFile(`${root}/app/company/[id]/CompanyGraphViewer.tsx`, "utf8");

  assert.doesNotMatch(source, /replaceGraph\(\{ nodes: \[\], edges: \[\] \}/);
  assert.match(source, /setLoadError/);
});

test("asset Excel conversion has no filename-only resume mode", async () => {
  const [viewSource, typesSource] = await Promise.all([
    readFile(`${root}/features/assets-excel/AssetExcelUtilityView.tsx`, "utf8"),
    readFile(`${root}/features/assets-excel/types.ts`, "utf8"),
  ]);

  assert.doesNotMatch(viewSource, /resume_failed_only|실패분 이어서 실행/);
  assert.doesNotMatch(typesSource, /resume_failed_only/);
});

test("job API responses keep their declared payload contracts", async () => {
  const [clientSource, pollingSource, streamingSource, sectionSource, downloadSource] = await Promise.all([
    readFile(`${root}/api/client.ts`, "utf8"),
    readFile(`${root}/hooks/useJobPolling.ts`, "utf8"),
    readFile(`${root}/hooks/useJobStreaming.ts`, "utf8"),
    readFile(`${root}/app/html-section-split/page.tsx`, "utf8"),
    readFile(`${root}/app/download/page.tsx`, "utf8"),
  ]);

  assert.doesNotMatch(clientSource, /response\.json\(\)\.catch\(\(\) => null\)/);
  assert.doesNotMatch(clientSource, /response\.text\(\)\.catch\(\(\) => ""\)/);
  assert.match(pollingSource, /onSuccess\(data\.result\)/);
  assert.doesNotMatch(pollingSource, /onSuccess\(data\.result \|\| data\)/);
  assert.doesNotMatch(streamingSource, /const data = await response\.json\(\);\s*onResult\(data\)/);
  assert.doesNotMatch(sectionSource, /setInspectResult\(data\.result \|\| data\)/);
  assert.doesNotMatch(downloadSource, /setResult\(data\.result \|\| data\)/);
});
