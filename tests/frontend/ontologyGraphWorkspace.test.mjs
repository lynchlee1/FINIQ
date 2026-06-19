import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const graphPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/page.tsx";
const workspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyGraphWorkspace.tsx";
const terminologyPath = "docs/ui-terminology.md";

test("graph page uses the real ontology workspace instead of test-data fixtures", async () => {
  const source = await readFile(graphPagePath, "utf8");

  assert.match(source, /OntologyGraphWorkspace/);
  assert.doesNotMatch(source, /OntologyQuantPlatformPanel/);
  assert.doesNotMatch(source, /CompanyGraphViewer/);
  assert.doesNotMatch(source, /TEST DATA/);
});

test("ontology graph workspace calls real data APIs and avoids synthetic copy", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /\/api\/ontology\/status/);
  assert.match(source, /\/api\/ontology\/companies/);
  assert.match(source, /\/api\/ontology\/company-panel/);
  assert.match(source, /주가-공시 차트/);
  assert.match(source, /공시 타임라인/);
  assert.match(source, /분석 요약/);
  assert.doesNotMatch(source, /TEST DATA/);
  assert.doesNotMatch(source, /Synthetic/);
  assert.doesNotMatch(source, /Export disabled for test data/);
});

test("ontology graph workspace uses one major box per row", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.doesNotMatch(source, /grid-cols-\[/);
  assert.doesNotMatch(source, /xl:grid-cols/);
  assert.doesNotMatch(source, /lg:grid-cols/);
  assert.doesNotMatch(source, /md:grid-cols-2/);
  assert.doesNotMatch(source, /grid-cols-2/);
  assert.doesNotMatch(source, /function StatusValue/);
  assert.doesNotMatch(source, /function SummaryMetric/);
});

test("ontology graph workspace splits long settings into modes", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /type WorkspaceMode/);
  assert.match(source, /WORKSPACE_MODES/);
  assert.match(source, /분석 조건/);
  assert.match(source, /activeMode === "analysis"/);
  assert.match(source, /activeMode === "companies"/);
  assert.match(source, /activeMode === "data"/);
});

test("ontology terminology documents the real-data workspace labels", async () => {
  const source = await readFile(terminologyPath, "utf8");

  assert.match(source, /\| Ontology real-data workspace \| Graph View \|/);
  assert.match(source, /\| Ontology data status \| 데이터 상태 \|/);
  assert.match(source, /\| Ontology event-price chart \| 주가-공시 차트 \|/);
  assert.match(source, /\| Ontology event timeline \| 공시 타임라인 \|/);
  assert.match(source, /\| Ontology analysis summary \| 분석 요약 \|/);
  assert.match(source, /\| Ontology workspace analysis mode \| 분석 \|/);
  assert.match(source, /\| Ontology workspace company mode \| 회사 \|/);
  assert.match(source, /\| Ontology workspace data mode \| 데이터 \|/);
  assert.match(source, /\| Ontology analysis filters \| 분석 조건 \|/);
});
