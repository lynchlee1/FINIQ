import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-graph/page.tsx";
const graphPath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyNodeGraph.tsx";

test("09 disclosure graph page builds, reloads, and renders the saved graph", async () => {
  const [pageSource, graphSource] = await Promise.all([
    readFile(pagePath, "utf8"),
    readFile(graphPath, "utf8"),
  ]);

  assert.match(pageSource, /title="공시 관계 그래프"/);
  assert.match(pageSource, /label: "작업공간 디렉토리"/);
  assert.match(pageSource, /\/api\/disclosures\/graph\/build/);
  assert.match(pageSource, /\/api\/disclosures\/graph\/load/);
  assert.match(pageSource, /그래프 생성/);
  assert.match(pageSource, /저장 결과 불러오기/);
  assert.match(pageSource, /<OntologyNodeGraph/);
  assert.match(pageSource, /graphData=\{graphData\}/);
  assert.match(pageSource, /dynamic<OntologyNodeGraphProps>/);
  assert.match(pageSource, /ssr: false/);

  assert.match(graphSource, /graphData\?: GraphData/);
  assert.match(graphSource, /STYLE_PRESETS\["Obsidian-like"\]/);
});
