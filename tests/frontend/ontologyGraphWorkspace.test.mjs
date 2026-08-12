import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const graphPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/page.tsx";
const workspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyGraphWorkspace.tsx";
const nodeGraphPath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyNodeGraph.tsx";
const chartPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/chart/page.tsx";
const chartWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/chart/OntologyChartWorkspace.tsx";
const analysisPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/page.tsx";
const analysisWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx";
const appFramePath = "frontend/finiq_GUI/apps/market-desk/src/components/layout/AppFrame.tsx";
const webAppFramePath = "frontend/finiq_GUI/packages/web-app/src/components/layout/AppFrame.tsx";
const navigationPath = "frontend/finiq_GUI/apps/market-desk/src/config/navigation.ts";
const backtestPath = "frontend/finiq_GUI/apps/market-desk/src/lib/disclosureBacktests.ts";
const terminologyPath = "DESIGN.md";

test("local backtest rejects an unknown calculation method", async () => {
  const source = await readFile(backtestPath, "utf8");

  assert.match(source, /if \(!method\) throw new Error\(`Unsupported backtest method:/);
  assert.doesNotMatch(source, /\?\? BACKTEST_METHODS\[0\]/);
});

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
  assert.match(source, /Graph View/);
  assert.match(source, /OntologyNodeGraph/);
  assert.doesNotMatch(source, /주가-공시 차트/);
  assert.doesNotMatch(source, /공시 타임라인/);
  assert.doesNotMatch(source, /renderPriceChart/);
  assert.doesNotMatch(source, /PriceChart/);
  assert.doesNotMatch(source, /공시 분석/);
  assert.doesNotMatch(source, /Triple Barrier/);
  assert.doesNotMatch(source, /TEST DATA/);
  assert.doesNotMatch(source, /Synthetic/);
  assert.doesNotMatch(source, /Export disabled for test data/);
});

test("ontology graph workspace restores the Obsidian-like node graph canvas", async () => {
  const [workspaceSource, nodeGraphSource] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(nodeGraphPath, "utf8"),
  ]);

  assert.match(workspaceSource, /import\("\.\/OntologyNodeGraph"\)/);
  assert.match(workspaceSource, /ssr: false/);
  assert.match(workspaceSource, /<OntologyNodeGraph/);
  assert.doesNotMatch(workspaceSource, /from "@finiq\/graph-viewer"/);
  assert.match(nodeGraphSource, /from "@finiq\/graph-viewer"/);
  assert.match(nodeGraphSource, /GraphCanvas/);
  assert.match(nodeGraphSource, /useGraphViewer/);
  assert.match(nodeGraphSource, /STYLE_PRESETS\["Obsidian-like"\]/);
  assert.match(nodeGraphSource, /buildOntologyGraphData/);
  assert.match(nodeGraphSource, /공시 관계 그래프/);
  assert.match(nodeGraphSource, /nodeTypes\.map/);
  assert.match(nodeGraphSource, /노드 검색/);
  assert.match(nodeGraphSource, /SettingsPanel/);
  assert.match(nodeGraphSource, /ActionDock/);
  assert.match(nodeGraphSource, /JobStatusLogger/);
  assert.match(nodeGraphSource, /undo/);
  assert.match(nodeGraphSource, /redo/);
  assert.match(nodeGraphSource, /showAll/);
  assert.match(nodeGraphSource, /shortestPath/);
  assert.match(nodeGraphSource, /jumpToNodeId/);
  assert.match(nodeGraphSource, /exportGraphJson/);
  assert.match(nodeGraphSource, /exportStyleJson/);
  assert.match(nodeGraphSource, /exportLayoutJson/);
  assert.match(nodeGraphSource, /exportVisibleSvg/);
  assert.match(nodeGraphSource, /exportCanvasPng/);
  assert.match(nodeGraphSource, /handleSaveLayout/);
  assert.match(nodeGraphSource, /handleLoadLayout/);
  assert.match(nodeGraphSource, /handleHideSelected/);
  assert.match(nodeGraphSource, /handleApplyNeighborhood/);
  assert.match(nodeGraphSource, /handleJumpSelected/);
  assert.match(nodeGraphSource, /localStorage\.setItem\(`ontology_graph_layout_/);
  assert.match(nodeGraphSource, /현재 레이아웃 저장/);
  assert.match(nodeGraphSource, /저장된 레이아웃 불러오기/);
  assert.match(nodeGraphSource, /숨김 초기화/);
  assert.equal(nodeGraphSource.match(/onClick=\{showAll\}/g)?.length, 1);
  assert.match(nodeGraphSource, /그래프 JSON 내보내기/);
  assert.match(nodeGraphSource, /SVG 내보내기/);
  assert.match(nodeGraphSource, /PNG 내보내기/);
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

test("ontology chart workspace exposes chart zoom sensitivity in the right settings dock", async () => {
  const source = await readFile(chartWorkspacePath, "utf8");

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

test("ontology graph workspace keeps the top selector graph-focused", async () => {
  const source = await readFile(workspacePath, "utf8");

  assert.match(source, /종목 선택/);
  assert.match(source, /placeholder="종목명 또는 A000000"/);
  assert.match(source, /selectedCompany\.stock_code/);
  assert.match(source, /normalizeStockCode/);
  assert.match(source, /loadCompanies/);
  assert.doesNotMatch(source, /formatCompanyOptionLabel/);
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

test("ontology routes use a wider app frame for canvas and chart workspaces", async () => {
  const [source, webAppFrameSource] = await Promise.all([
    readFile(appFramePath, "utf8"),
    readFile(webAppFramePath, "utf8"),
  ]);

  assert.match(source, /<WebAppFrame topbar=\{<Topbar \/>}/);
  assert.match(webAppFrameSource, /max-w-\[92rem\]/);
});

test("ontology chart workspace defaults to full range and provides disclosure analysis", async () => {
  const [chartSource, analysisSource] = await Promise.all([
    readFile(chartWorkspacePath, "utf8"),
    readFile(analysisWorkspacePath, "utf8"),
  ]);

  assert.match(chartSource, /전체 기간/);
  assert.match(analysisSource, /공시 분석/);
  assert.match(analysisSource, /Triple Barrier 실행/);
  assert.match(analysisSource, /\/api\/ontology\/triple-barrier\/run/);
  assert.doesNotMatch(chartSource, /currentYearStart/);
  assert.doesNotMatch(chartSource, /todayInputValue/);
  assert.doesNotMatch(chartSource, /start_date: startDate/);
  assert.doesNotMatch(chartSource, /end_date: endDate/);
});

test("disclosure analysis groups execution controls by workflow", async () => {
  const source = await readFile(analysisWorkspacePath, "utf8");
  const executionTargetStart = source.indexOf("1. 실행 대상");
  const disclosureScopeStart = source.indexOf("2. 공시 범위");
  const parameterStart = source.indexOf("3. Triple Barrier 설정");
  const summaryStart = source.indexOf("저장 결과 요약");
  const tableStart = source.indexOf("결과 테이블");

  assert.ok(executionTargetStart > -1);
  assert.ok(disclosureScopeStart > executionTargetStart);
  assert.ok(parameterStart > disclosureScopeStart);
  assert.ok(summaryStart > parameterStart);
  assert.ok(tableStart > summaryStart);
  assert.match(source, /검사 대상 이벤트/);
  assert.match(source, /Triple Barrier 실행/);
});

test("ontology chart workspace can expand the price chart without third-party branding", async () => {
  const source = await readFile(chartWorkspacePath, "utf8");

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

test("ontology chart workspace manages chart conditions in a top filter box", async () => {
  const source = await readFile(chartWorkspacePath, "utf8");
  const conditionBoxStart = source.indexOf("FILTERS");
  const chartCardStart = source.indexOf("주가-공시 차트", conditionBoxStart);
  const timelineStart = source.indexOf("공시 타임라인", chartCardStart);
  const conditionBoxSource = source.slice(conditionBoxStart, chartCardStart);
  const chartCardSource = source.slice(chartCardStart, timelineStart);

  assert.notEqual(conditionBoxStart, -1);
  assert.match(conditionBoxSource, /공시 조건/);
  assert.match(conditionBoxSource, /회사명/);
  assert.match(conditionBoxSource, /공시 선택/);
  assert.match(conditionBoxSource, /ontology-page-card-content space-y-4/);
  assert.match(conditionBoxSource, /border-t border-slate-200/);
  assert.match(conditionBoxSource, /ontology-chart-disclosure-group/);
  assert.match(conditionBoxSource, /DISCLOSURE_GROUP_ALL/);
  assert.match(conditionBoxSource, /renderChartControls/);
  assert.doesNotMatch(chartCardSource, /CHART_TYPE_OPTIONS\.map/);
  assert.doesNotMatch(chartCardSource, /DISPLAY_FREQUENCY_OPTIONS\.map/);
  assert.doesNotMatch(chartCardSource, /setChartFullscreen/);
});

test("ontology chart workspace handles loading and frequency controls", async () => {
  const source = await readFile(chartWorkspacePath, "utf8");

  assert.match(source, /chartIsLoading/);
  assert.match(source, /loadingCompanies/);
  assert.match(source, /requestedPanelKey/);
  assert.match(source, /setDisplayFrequency/);
  assert.match(source, /DISPLAY_FREQUENCY_OPTIONS/);
  assert.match(source, /disclosureGroup/);
  assert.match(source, /status\?\.disclosure_groups/);
  assert.match(source, /disclosure_group: disclosureGroup/);
  assert.match(source, /일봉/);
  assert.match(source, /3일봉/);
  assert.match(source, /5일봉/);
  assert.match(source, /7일봉/);
  assert.match(source, /20일봉/);
  assert.match(source, /월봉/);
  assert.match(source, /<select\s+aria-label="일봉\/3일봉\/5일봉\/7일봉\/20일봉\/월봉"/);
  assert.match(source, /setDisplayFrequency\(event\.target\.value as \(typeof DISPLAY_FREQUENCY_OPTIONS\)\[number\]\)/);
  assert.match(source, /display_frequency: displayFrequency/);
});

test("ontology chart workspace keeps empty search state until the user searches", async () => {
  const source = await readFile(chartWorkspacePath, "utf8");

  assert.doesNotMatch(source, /loadStatus\(\);\s*loadCompanies\(\);/);
  assert.match(source, /loadStatus\(\);/);
  assert.match(source, /if \(!keyword\.trim\(\)\)/);
  assert.match(source, /setSelectedCompany\(null\)/);
  assert.match(source, /setPanel\(null\)/);
  assert.match(source, /검색한 종목이 없습니다/);
  assert.match(source, /isStockCodeKeyword/);
  assert.doesNotMatch(source, /keywordText\.startsWith\("A"\)/);
});

test("ontology workspaces only strip A prefix from stock-code keywords", async () => {
  const [graphSource, chartSource, analysisSource] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(chartWorkspacePath, "utf8"),
    readFile(analysisWorkspacePath, "utf8"),
  ]);

  for (const source of [graphSource, chartSource]) {
    assert.match(source, /function isStockCodeKeyword\(value: string\) \{\s+return \/\^A\[A-Z0-9\]\{6\}\$\/\.test\(value\.trim\(\)\.toUpperCase\(\)\);\s+\}/);
    assert.match(source, /isStockCodeKeyword\(keywordText\) \? normalizeStockCode\(keywordText\)\.slice\(1\) : keyword\.trim\(\)/);
    assert.doesNotMatch(source, /keywordText\.startsWith\("A"\)/);
    assert.doesNotMatch(source, /replace\(\/\\D/);
  }
  assert.match(analysisSource, /function isStockCodeKeyword\(value: string\) \{\s+return \/\^A\[A-Z0-9\]\{6\}\$\/\.test\(value\.trim\(\)\.toUpperCase\(\)\);\s+\}/);
  assert.match(analysisSource, /isStockCodeKeyword\(keywordText\) \? normalizeStockCode\(keywordText\)\.slice\(1\) : runKeyword\.trim\(\)/);
  assert.match(analysisSource, /isStockCodeKeyword\(keywordText\) \? normalizeStockCode\(keywordText\)\.slice\(1\) : resultKeyword\.trim\(\)/);
  assert.doesNotMatch(analysisSource, /keywordText\.startsWith\("A"\)/);
  assert.doesNotMatch(analysisSource, /replace\(\/\\D/);
});

test("ontology disclosure analysis keeps empty search state until the user searches", async () => {
  const source = await readFile(analysisWorkspacePath, "utf8");

  assert.doesNotMatch(source, /useEffect\(\(\) => \{\s*loadRunCompanies\(\);/);
  assert.doesNotMatch(source, /useEffect\(\(\) => \{\s*loadResultCompanies\(\);/);
  assert.match(source, /if \(!runKeyword\.trim\(\)\)/);
  assert.match(source, /if \(!resultKeyword\.trim\(\)\)/);
  assert.match(source, /setSelectedRunCompany\(null\)/);
  assert.match(source, /setSelectedResultCompany\(null\)/);
  assert.match(source, /setPanel\(null\)/);
  assert.match(source, /실행할 종목이 없습니다/);
  assert.match(source, /조회할 종목이 없습니다/);
  assert.match(source, /isStockCodeKeyword/);
  assert.doesNotMatch(source, /keywordText\.startsWith\("A"\)/);
});

test("ontology chart workspace offers a close-price line view", async () => {
  const source = await readFile(chartWorkspacePath, "utf8");

  assert.match(source, /chartType/);
  assert.match(source, /setChartType/);
  assert.match(source, /"candlestick"/);
  assert.match(source, /"line"/);
  assert.match(source, /캔들/);
  assert.match(source, /종가선/);
  assert.match(source, /<select\s+aria-label="캔들\/종가선"/);
  assert.match(source, /setChartType\(event\.target\.value as \(typeof CHART_TYPE_OPTIONS\)\[number\]\["value"\]\)/);
  assert.match(source, /chartType=\{chartType\}/);
});

test("ontology graph workspace aborts in-flight API loads when leaving the page", async () => {
  const [graphSource, chartSource] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(chartWorkspacePath, "utf8"),
  ]);
  const source = `${graphSource}\n${chartSource}`;

  assert.match(source, /AbortController/);
  assert.match(source, /useRef/);
  assert.match(source, /statusAbortControllerRef/);
  assert.match(source, /companiesAbortControllerRef/);
  assert.match(source, /panelAbortControllerRef/);
  assert.match(source, /signal: controller\.signal/);
  assert.match(source, /controller\.signal\.aborted/);
  assert.match(source, /err instanceof DOMException && err\.name === "AbortError"/);
  assert.match(source, /statusAbortControllerRef\.current\?\.abort\(\)/);
  assert.match(source, /companiesAbortControllerRef\.current\?\.abort\(\)/);
  assert.match(source, /panelAbortControllerRef\.current\?\.abort\(\)/);
});

test("ontology workflow separates relationship graph and chart routes", async () => {
  const [navigationSource, graphPageSource, chartPageSource, chartWorkspaceSource] = await Promise.all([
    readFile(navigationPath, "utf8"),
    readFile(graphPagePath, "utf8"),
    readFile(chartPagePath, "utf8"),
    readFile(chartWorkspacePath, "utf8"),
  ]);

  assert.match(navigationSource, /basePath: "\/graph\/chart"/);
  assert.match(navigationSource, /\{ href: "\/graph\/chart", step: 1, label: "Chart View" \}/);
  assert.match(navigationSource, /\{ href: "\/graph", step: 2, label: "Graph View" \}/);
  assert.match(navigationSource, /\{ href: "\/graph\/analysis", step: 3, label: "공시 분석" \}/);
  assert.match(graphPageSource, /OntologyGraphWorkspace/);
  assert.match(chartPageSource, /OntologyChartWorkspace/);
  assert.match(chartPageSource, /WorkflowPageShell/);
  assert.match(chartPageSource, /workflowId="ontology"/);
  assert.match(chartWorkspaceSource, /Chart View/);
  assert.match(chartWorkspaceSource, /주가-공시 차트/);
  assert.doesNotMatch(chartWorkspaceSource, /OntologyNodeGraph/);
});

test("ontology disclosure analysis has a dedicated API-backed page", async () => {
  const [pageSource, workspaceSource] = await Promise.all([
    readFile(analysisPagePath, "utf8"),
    readFile(analysisWorkspacePath, "utf8"),
  ]);

  assert.match(pageSource, /DisclosureAnalysisWorkspace/);
  assert.match(pageSource, /WorkflowPageShell/);
  assert.match(pageSource, /workflowId="ontology"/);
  assert.match(workspaceSource, /공시 분석/);
  assert.match(workspaceSource, /apiPost/);
  assert.match(workspaceSource, /loadTripleBarrierResults/);
  assert.doesNotMatch(workspaceSource, /BACKTEST_METHODS/);
  assert.doesNotMatch(workspaceSource, /runDisclosureBacktest/);
});

test("ontology disclosure analysis exposes result review and category-scoped execution", async () => {
  const source = await readFile(analysisWorkspacePath, "utf8");

  assert.match(source, /실행 설정/);
  assert.match(source, /저장 결과/);
  assert.match(source, /저장 결과 요약/);
  assert.match(source, /저장 결과 조회/);
  assert.match(source, /실행 종목 선택/);
  assert.match(source, /실행 대상 검색/);
  assert.match(source, /결과 종목 선택/);
  assert.match(source, /저장 결과 검색/);
  assert.match(source, /선택 종목 결과 조회/);
  assert.match(source, /저장 결과 보기/);
  assert.match(source, /검사 대상 이벤트/);
  assert.match(source, /공시 선택/);
  assert.match(source, /formatDisclosureGroupLabel/);
  assert.match(source, /disclosure-analysis-disclosure-group/);
  assert.match(source, /<option key={group} value={group}>/);
  assert.match(source, /ontology-scroll-list/);
  assert.match(source, /disclosureGroup/);
  assert.match(source, /status\?\.disclosure_groups/);
  assert.match(source, /selectedAnalysisMode/);
  assert.match(source, /selectedRunCompany/);
  assert.match(source, /selectedResultCompany/);
  assert.match(source, /runKeyword/);
  assert.match(source, /resultKeyword/);
  assert.match(source, /disclosure_group: disclosureGroup/);
  assert.match(source, /setTripleBarrierResult\(null\);/);
  assert.doesNotMatch(source, /const \[keyword, setKeyword\]/);
  assert.doesNotMatch(source, /const \[selectedCompany, setSelectedCompany\]/);
  assert.doesNotMatch(source, /disclosure_group: "전체"/);
});

test("ontology terminology documents the real-data workspace labels", async () => {
  const source = await readFile(terminologyPath, "utf8");

  assert.match(source, /\| Ontology real-data workspace \| Graph View \|/);
  assert.match(source, /\| Ontology chart workspace \| Chart View \|/);
  assert.match(source, /\| Ontology data status \| 데이터 상태 \|/);
  assert.match(source, /\| Ontology company selector \| 회사 선택 \|/);
  assert.match(source, /\| Ontology stock selector \| 종목 선택 \|/);
  assert.match(source, /\| Ontology node graph \| 공시 관계 그래프 \|/);
  assert.match(source, /\| Ontology node search \| 노드 검색 \|/);
  assert.match(source, /\| Ontology graph unpin action \| 핀 해제 \|/);
  assert.match(source, /\| Ontology event-price chart \| 주가-공시 차트 \|/);
  assert.match(source, /\| Ontology event timeline \| 공시 타임라인 \|/);
  assert.match(source, /\| Ontology disclosure analysis \| 공시 분석 \|/);
  assert.match(source, /\| Ontology triple barrier execution action \| Triple Barrier 실행 \|/);
  assert.match(source, /\| Ontology triple barrier execution company selector \| 실행 종목 선택 \|/);
  assert.match(source, /\| Ontology triple barrier execution company search action \| 실행 대상 검색 \|/);
  assert.match(source, /\| Ontology triple barrier result company selector \| 결과 종목 선택 \|/);
  assert.match(source, /\| Ontology triple barrier result company search action \| 저장 결과 검색 \|/);
  assert.match(source, /\| Ontology triple barrier selected result lookup action \| 선택 종목 결과 조회 \|/);
  assert.match(source, /\| Ontology triple barrier event basis \| 이벤트 기준일 \|/);
  assert.match(source, /\| Ontology triple barrier price basis \| 가격 기준 \|/);
  assert.match(source, /\| Ontology triple barrier result table \| 결과 테이블 \|/);
  assert.match(source, /\| Ontology chart frequency selector \| 일봉\/3일봉\/5일봉\/7일봉\/20일봉\/월봉 \|/);
  assert.match(source, /\| Ontology chart type selector \| 캔들\/종가선 \|/);
  assert.match(source, /\| Ontology final report marker \| 최종보고서 \|/);
  assert.match(source, /\| Ontology full date range \| 전체 기간 \|/);
  assert.match(source, /\| Ontology chart fullscreen action \| 전체화면 \|/);
  assert.match(source, /\| Ontology chart exit fullscreen action \| 전체화면 닫기 \|/);
  assert.match(source, /\| Ontology chart zoom sensitivity \| 확대\/축소 민감도 \|/);
  assert.match(source, /\| Ontology chart marker style section \| 공시 마커 스타일 \|/);
  assert.match(source, /\| Ontology chart marker style target \| 스타일 대상 \|/);
  assert.match(source, /\| Ontology chart marker placement setting \| 공시 마커 위치 \|/);
  assert.match(source, /\| Ontology chart marker shape setting \| 공시 마커 모양 \|/);
  assert.match(source, /\| Ontology chart marker color setting \| 색상 \|/);
  assert.match(source, /\| Ontology chart marker size setting \| 크기 \|/);
  assert.match(source, /\| Ontology chart marker line width setting \| 선 두께 \|/);
  assert.doesNotMatch(source, /\| Ontology chart view mode \| 차트 \|/);
  assert.doesNotMatch(source, /\| Ontology analysis summary \| 분석 요약 \|/);
  assert.doesNotMatch(source, /\| Ontology analysis filters \| 분석 조건 \|/);
  assert.doesNotMatch(source, /\| Ontology workspace analysis mode \| 분석 \|/);
  assert.doesNotMatch(source, /\| Ontology workspace company mode \| 회사 \|/);
  assert.doesNotMatch(source, /\| Ontology workspace data mode \| 데이터 \|/);
});

test("ontology chart settings expose per-disclosure marker styles in one compact section", async () => {
  const source = await readFile(chartWorkspacePath, "utf8");

  assert.match(source, /MARKER_PLACEMENT_OPTIONS/);
  assert.match(source, /MARKER_SHAPE_OPTIONS/);
  assert.match(source, /MARKER_STYLE_GROUP_ALL/);
  assert.match(source, /markerStyleGroups/);
  assert.match(source, /공시 마커 스타일/);
  assert.match(source, /스타일 대상/);
  assert.match(source, /모양/);
  assert.match(source, /위치/);
  assert.match(source, /색상/);
  assert.match(source, /크기/);
  assert.match(source, /선 두께/);
  assert.match(source, /ontology-panel ontology-panel-section/);
  assert.match(source, /ontology-form-grid sm:grid-cols-2/);
  assert.match(source, /h-8 rounded-md/);
  assert.match(source, /aria-label="공시 마커 스타일 미리보기"/);
  assert.match(source, /value: "paneTop", label: "차트 상단"/);
  assert.match(source, /value: "paneBottom", label: "차트 하단"/);
  assert.match(source, /value: "arrowDown", label: "아래 삼각형"/);
  assert.match(source, /const \[activeMarkerStyleGroup, setActiveMarkerStyleGroup\]/);
  assert.match(source, /const \[markerStyleDefault, setMarkerStyleDefault\]/);
  assert.match(source, /const \[markerStylesByGroup, setMarkerStylesByGroup\]/);
  assert.match(source, /updateActiveMarkerStyle/);
  assert.match(source, /markerStyleDefault=\{markerStyleDefault\}/);
  assert.match(source, /markerStylesByGroup=\{markerStylesByGroup\}/);
  assert.doesNotMatch(source, /markerPlacement=\{markerPlacement\}/);
  assert.doesNotMatch(source, /markerShape=\{markerShape\}/);
});

test("disclosure analysis page runs and displays persisted triple barrier results", async () => {
  const [analysisSource, terminologySource] = await Promise.all([
    readFile(analysisWorkspacePath, "utf8"),
    readFile(terminologyPath, "utf8"),
  ]);

  assert.match(terminologySource, /Triple Barrier 실행/);
  assert.match(analysisSource, /apiPost/);
  assert.match(analysisSource, /\/api\/ontology\/triple-barrier\/run/);
  assert.match(analysisSource, /\/api\/ontology\/triple-barrier\/results/);
  assert.match(analysisSource, /event_time_basis/);
  assert.match(analysisSource, /price_basis/);
  assert.match(analysisSource, /upper_pct/);
  assert.match(analysisSource, /lower_pct/);
  assert.match(analysisSource, /vertical_days/);
  assert.match(analysisSource, /disclosure_ids/);
  for (const label of [
    "공시 ID",
    "종목코드",
    "종목명",
    "공시일",
    "이벤트 가격",
    "upper barrier 가격",
    "lower barrier 가격",
    "vertical barrier 날짜",
    "최초 도달 barrier",
    "최초 도달 날짜",
    "최초 도달 가격",
    "수익률",
    "label",
    "계산 상태",
    "에러 메시지",
  ]) {
    assert.match(analysisSource, new RegExp(label));
  }
  assert.doesNotMatch(analysisSource, /runDisclosureBacktest/);
});
