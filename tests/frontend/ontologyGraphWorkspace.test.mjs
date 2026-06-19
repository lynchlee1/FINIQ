import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const graphPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/page.tsx";
const workspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyGraphWorkspace.tsx";
const analysisPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/page.tsx";
const analysisWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx";
const backtestPath = "frontend/finiq_GUI/apps/market-desk/src/lib/disclosureBacktests.ts";
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
  assert.doesNotMatch(source, /공시 분석/);
  assert.doesNotMatch(source, /Triple Barrier/);
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
  assert.match(source, /placeholder="종목명 또는 A000000"/);
  assert.match(source, /selectedCompany\.stock_code/);
  assert.match(source, /normalizeStockCode/);
  assert.match(source, /loadCompanies/);
  assert.doesNotMatch(source, /formatCompanyOptionLabel/);
  assert.doesNotMatch(source, /<CardTitle[\s\S]*Graph View/);
  assert.doesNotMatch(source, /<select/);
  assert.doesNotMatch(source, /코스피/);
  assert.doesNotMatch(source, /종목 없음/);
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
  const [source, analysisSource, backtestSource] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(analysisWorkspacePath, "utf8"),
    readFile(backtestPath, "utf8"),
  ]);

  assert.match(source, /전체 기간/);
  assert.match(analysisSource, /공시 분석/);
  assert.match(analysisSource, /BACKTEST_METHODS/);
  assert.match(analysisSource, /runDisclosureBacktest/);
  assert.match(backtestSource, /triple-barrier/);
  assert.match(backtestSource, /upperBarrier/);
  assert.match(backtestSource, /lowerBarrier/);
  assert.match(backtestSource, /barrierHorizon/);
  assert.match(backtestSource, /상승 돌파/);
  assert.match(backtestSource, /하락 돌파/);
  assert.match(backtestSource, /기간 만료/);
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
  assert.match(source, /chartMetaText/);
  assert.match(source, /showHeader=\{false\}/);
  assert.doesNotMatch(source, /KIND 공시 이벤트와 Quantiwise 가격 데이터를 같은 기간 축에서 비교합니다/);
  assert.doesNotMatch(source, /TradingView/);
  assert.doesNotMatch(source, /tv-lightweight-charts/);
});

test("ontology graph workspace handles loading and frequency controls", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /chartIsLoading/);
  assert.match(source, /loadingCompanies/);
  assert.match(source, /requestedPanelKey/);
  assert.match(source, /setDisplayFrequency/);
  assert.match(source, /DISPLAY_FREQUENCY_OPTIONS/);
  assert.match(source, /일봉/);
  assert.match(source, /5일봉/);
  assert.match(source, /20일봉/);
  assert.match(source, /월봉/);
  assert.match(source, /display_frequency: displayFrequency/);
});

test("ontology disclosure analysis has a dedicated page and extensible method registry", async () => {
  const [pageSource, workspaceSource, backtestSource] = await Promise.all([
    readFile(analysisPagePath, "utf8"),
    readFile(analysisWorkspacePath, "utf8"),
    readFile(backtestPath, "utf8"),
  ]);

  assert.match(pageSource, /DisclosureAnalysisWorkspace/);
  assert.match(workspaceSource, /공시 분석/);
  assert.match(workspaceSource, /methodId/);
  assert.match(workspaceSource, /BACKTEST_METHODS/);
  assert.match(workspaceSource, /runDisclosureBacktest/);
  assert.match(backtestSource, /type BacktestMethodDefinition/);
  assert.match(backtestSource, /BACKTEST_METHODS/);
  assert.match(backtestSource, /runDisclosureBacktest/);
  assert.match(backtestSource, /runTripleBarrierMethod/);
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
  assert.match(source, /\| Ontology chart frequency selector \| 일봉\/5일봉\/20일봉\/월봉 \|/);
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
