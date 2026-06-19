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
  assert.match(source, /공시 분석/);
  assert.match(source, /Triple Barrier/);
  assert.doesNotMatch(source, /TEST DATA/);
  assert.doesNotMatch(source, /Synthetic/);
  assert.doesNotMatch(source, /Export disabled for test data/);
});

test("ontology graph workspace uses one major box per row", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.doesNotMatch(source, /xl:grid-cols/);
  assert.doesNotMatch(source, /lg:grid-cols/);
  assert.doesNotMatch(source, /md:grid-cols-2/);
  assert.doesNotMatch(source, /grid-cols-2/);
  assert.doesNotMatch(source, /function StatusValue/);
  assert.doesNotMatch(source, /function SummaryMetric/);
});

test("ontology graph workspace exposes chart zoom sensitivity in the right settings dock", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /ActionDock/);
  assert.match(source, /settingsTitle="설정"/);
  assert.match(source, /chartZoomSensitivity/);
  assert.match(source, /ontology-chart-zoom-sensitivity/);
  assert.match(source, /ontology-chart-zoom-sensitivity-value/);
  assert.match(source, /type="number"/);
  assert.match(source, /className="h-8 w-20 text-right tabular-nums dark:bg-\[#0d1117\] dark:border-\[#30363d\] dark:text-slate-200"/);
  assert.match(source, /확대\/축소 민감도/);
  assert.match(source, /onInput=\{handleChartZoomSensitivityChange\}/);
  assert.match(source, /zoomSensitivity=\{chartZoomSensitivity\}/);
});

test("ontology graph workspace keeps the top selector chart-focused", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /종목 선택/);
  assert.match(source, /selectedCompany\.stock_code/);
  assert.match(source, /normalizeStockCode/);
  assert.match(source, /formatCompanyOptionLabel/);
  assert.doesNotMatch(source, /type ChartViewMode/);
  assert.doesNotMatch(source, /CHART_VIEW_MODES/);
  assert.doesNotMatch(source, /activeChartView/);
  assert.doesNotMatch(source, /setActiveChartView/);
  assert.doesNotMatch(source, /WorkspaceMode/);
  assert.doesNotMatch(source, /WORKSPACE_MODES/);
  assert.doesNotMatch(source, /activeMode/);
  assert.doesNotMatch(source, /분석 조건/);
  assert.doesNotMatch(source, /분석 요약/);
  assert.doesNotMatch(source, /시작일/);
  assert.doesNotMatch(source, /종료일/);
  assert.doesNotMatch(source, /데이터 상태/);
});

test("ontology graph workspace defaults to full range and provides disclosure analysis", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /전체 기간/);
  assert.match(source, /tripleBarrierResults/);
  assert.match(source, /upperBarrier/);
  assert.match(source, /lowerBarrier/);
  assert.match(source, /barrierHorizon/);
  assert.match(source, /상승 돌파/);
  assert.match(source, /하락 돌파/);
  assert.match(source, /기간 만료/);
  assert.doesNotMatch(source, /currentYearStart/);
  assert.doesNotMatch(source, /todayInputValue/);
  assert.doesNotMatch(source, /start_date: startDate/);
  assert.doesNotMatch(source, /end_date: endDate/);
});

test("ontology graph workspace can expand the price chart without third-party branding", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /chartFullscreen/);
  assert.match(source, /setChartFullscreen/);
  assert.match(source, /전체화면/);
  assert.match(source, /전체화면 닫기/);
  assert.match(source, /fixed inset-0 z-50/);
  assert.match(source, /renderPriceChart/);
  assert.doesNotMatch(source, /TradingView/);
  assert.doesNotMatch(source, /tv-lightweight-charts/);
});

test("ontology terminology documents the real-data workspace labels", async () => {
  const source = await readFile(terminologyPath, "utf8");

  assert.match(source, /\| Ontology real-data workspace \| Graph View \|/);
  assert.match(source, /\| Ontology data status \| 데이터 상태 \|/);
  assert.match(source, /\| Ontology company selector \| 회사 선택 \|/);
  assert.match(source, /\| Ontology stock selector \| 종목 선택 \|/);
  assert.match(source, /\| Ontology event-price chart \| 주가-공시 차트 \|/);
  assert.match(source, /\| Ontology event timeline \| 공시 타임라인 \|/);
  assert.match(source, /\| Ontology disclosure analysis \| 공시 분석 \|/);
  assert.match(source, /\| Ontology full date range \| 전체 기간 \|/);
  assert.match(source, /\| Ontology chart fullscreen action \| 전체화면 \|/);
  assert.match(source, /\| Ontology chart exit fullscreen action \| 전체화면 닫기 \|/);
  assert.match(source, /\| Ontology chart zoom sensitivity \| 확대\/축소 민감도 \|/);
  assert.doesNotMatch(source, /\| Ontology chart view mode \| 차트 \|/);
  assert.doesNotMatch(source, /\| Ontology analysis summary \| 분석 요약 \|/);
  assert.doesNotMatch(source, /\| Ontology analysis filters \| 분석 조건 \|/);
  assert.doesNotMatch(source, /\| Ontology workspace analysis mode \| 분석 \|/);
  assert.doesNotMatch(source, /\| Ontology workspace company mode \| 회사 \|/);
  assert.doesNotMatch(source, /\| Ontology workspace data mode \| 데이터 \|/);
});
