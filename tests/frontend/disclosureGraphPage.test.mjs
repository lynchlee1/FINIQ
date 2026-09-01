import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-graph/page.tsx";
const graphPath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyNodeGraph.tsx";
const monitorPath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-graph/GovernanceTransitionMonitor.tsx";
const modelPath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-graph/governanceTransitionModel.ts";
const testDataPath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-graph/crowdworksGovernanceTestData.ts";
const evidenceIndexPath = "docs/disclosures/09-disclosure-graph/evidence/crowdworks-daeyang/README.md";

test("09 disclosure graph page builds, reloads, and renders the saved graph", async () => {
  const [pageSource, graphSource, monitorSource, modelSource, testDataSource, evidenceIndexSource] = await Promise.all([
    readFile(pagePath, "utf8"),
    readFile(graphPath, "utf8"),
    readFile(monitorPath, "utf8"),
    readFile(modelPath, "utf8"),
    readFile(testDataPath, "utf8"),
    readFile(evidenceIndexPath, "utf8"),
  ]);

  assert.match(pageSource, /title="공시 관계 그래프"/);
  assert.match(pageSource, /label: DATA_PATH_LABELS\.workspace/);
  assert.match(pageSource, /\/api\/disclosures\/graph\/build/);
  assert.match(pageSource, /\/api\/disclosures\/graph\/load/);
  assert.match(pageSource, /그래프 생성/);
  assert.match(pageSource, /저장 결과 불러오기/);
  assert.match(pageSource, /<OntologyNodeGraph/);
  assert.match(pageSource, /graphData=\{graphData\}/);
  assert.match(pageSource, /dynamic<OntologyNodeGraphProps>/);
  assert.match(pageSource, /ssr: false/);
  assert.match(pageSource, /<GovernanceTransitionMonitor caseData=\{DAEYANG_CROWDWORKS_TEST_CASE\}/);
  assert.match(pageSource, /테스트 데이터 보기/);
  assert.match(pageSource, /DAEYANG_CROWDWORKS_GOVERNANCE_GRAPH/);

  assert.match(graphSource, /graphData\?: GraphData/);
  assert.match(graphSource, /STYLE_PRESETS\["Obsidian-like"\]/);

  assert.match(monitorSource, /지배구조 변화 모니터/);
  assert.match(monitorSource, /근거 원장/);
  assert.match(monitorSource, /caseData\.comparisonPanels\.map/);
  assert.match(monitorSource, /\.\.\.caseData\.categories/);
  assert.match(monitorSource, /caseData\.events/);
  assert.doesNotMatch(monitorSource, /대양금속|영풍제지|크라우드웍스/);
  assert.doesNotMatch(monitorSource, /lucide-react/);
  assert.doesNotMatch(monitorSource, /rounded-lg/);
  assert.match(modelSource, /export type GovernanceTransitionCase/);
  assert.match(modelSource, /comparisonPanels: GovernanceComparisonPanel\[\]/);
  assert.match(modelSource, /events: GovernanceTransitionEvent\[\]/);
  assert.match(testDataSource, /DAEYANG_CROWDWORKS_TEST_CASE/);
  assert.match(testDataSource, /원래 현금은 약 60억원/);
  assert.match(testDataSource, /22만7,448회 주문/);
  assert.match(testDataSource, /크라우드웍스 제2회차 CB/);
  assert.match(testDataSource, /CONTROLLING_SHAREHOLDER_OF/);
  assert.match(testDataSource, /SUBMITTED_MANIPULATIVE_ORDERS_FOR/);
  assert.match(testDataSource, /exact_fund_match_confirmed: false/);
  assert.match(evidenceIndexSource, /2024-02-14-seoul-southern-prosecution-youngpoong\.pdf/);
  assert.match(evidenceIndexSource, /91931861f3c823ac2bdcdcdc9465a698ef677aa5b9fb1d1795651f5355b0cbaa/);
  assert.match(evidenceIndexSource, /유죄 확정 사실이 아니다/);
});
