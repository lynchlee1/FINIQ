import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlSectionSplitPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
const tablePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx";
const htmlWorkflowTemplatePath = "frontend/finiq_GUI/apps/market-desk/src/components/html-workflow/HtmlWorkflowTemplate.tsx";
const filterPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx";
const utilityPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/utility/page.tsx";
const assetsExcelViewPath = "frontend/finiq_GUI/apps/market-desk/src/features/assets-excel/AssetExcelUtilityView.tsx";
const graphWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyGraphWorkspace.tsx";
const graphNodePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyNodeGraph.tsx";
const chartWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/chart/OntologyChartWorkspace.tsx";
const analysisWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx";

test("html section split path fields stack vertically", async () => {
  const source = await readFile(htmlSectionSplitPath, "utf8");
  const pathFieldsBlock = source.match(/const folderPathFields:[\s\S]*?const splitOptionFields:/)?.[0] ?? "";

  assert.match(pathFieldsBlock, /id: "inputDirectory"[\s\S]*?span: 4/);
});

test("html section split uses shared data path and execution cards", async () => {
  const source = await readFile(htmlSectionSplitPath, "utf8");

  assert.match(source, /title="데이터 경로"/);
  assert.match(source, /title="작업 실행"/);
  assert.match(source, /소스 불러오기/);
  assert.match(source, /FolderOpen/);
  assert.match(source, /\/api\/disclosures\/html\/sections\/save\/start/);
  assert.match(source, /onClick=\{startSave\}[\s\S]*?\n\s*실행\s*\n/);
  assert.ok(
    source.indexOf("<HtmlSectionSplitResults") < source.indexOf('title="작업 실행"'),
    "개별 공시 창은 실행 버튼 위에 있어야 합니다.",
  );
  assert.doesNotMatch(source, /소스 새로고침/);
  assert.doesNotMatch(source, /RefreshCw/);
  assert.match(source, /<Square className="mr-2 h-4 w-4" \/>/);
  assert.match(source, /UI_TEXT\.actions\.cancelJob/);
  assert.match(source, /inspectAbortControllerRef\.current\?\.abort\(\)/);
  assert.doesNotMatch(source, /title="폴더 선택"/);
});

test("html section split exposes worker count setting and uses background inspect job", async () => {
  const source = await readFile(htmlSectionSplitPath, "utf8");

  assert.match(source, /const \[workers, setWorkers\] = useState\("8"\)/);
  assert.match(source, /label: "병렬 처리 개수"/);
  assert.match(source, /\/api\/disclosures\/html\/sections\/inspect\/start/);
  assert.match(source, /workers: parseOptionalNumber\(workers\)/);
  assert.match(source, /\/api\/disclosures\/html\/cancel/);
  assert.match(source, /setInspectResult\(data\.result \|\| data\)/);
});

test("html section split keeps job status only in the action dock", async () => {
  const source = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx",
    "utf8",
  );
  const mainResultsBlock = source.match(/export function HtmlSectionSplitResults[\s\S]*?export function HtmlSectionSplitActionDock/)?.[0] ?? "";
  const actionDockBlock = source.match(/export function HtmlSectionSplitActionDock[\s\S]*$/)?.[0] ?? "";

  assert.doesNotMatch(mainResultsBlock, /title="작업 상태"/);
  assert.match(actionDockBlock, /activityContent=\{/);
  assert.match(actionDockBlock, /<JobStatusLogger/);
});

test("disclosure table conversion path fields stack vertically", async () => {
  const source = await readFile(tablePagePath, "utf8");

  assert.match(source, /<CardTitle className="dark:text-white">데이터 경로<\/CardTitle>/);
  assert.doesNotMatch(source, /<div className="grid gap-4 md:grid-cols-2">/);
});

test("data path cards omit descriptions and keep compact title spacing", async () => {
  const tableSource = await readFile(tablePagePath, "utf8");
  const sectionSplitSource = await readFile(htmlSectionSplitPath, "utf8");
  const downloadSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-download/_components/HtmlDownloadPageView.tsx",
    "utf8",
  );
  const templateSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/components/html-workflow/HtmlWorkflowTemplate.tsx",
    "utf8",
  );

  const tableDataPathCard = tableSource.match(/<Card[\s\S]*?<CardTitle className="dark:text-white">데이터 경로<\/CardTitle>[\s\S]*?<\/Card>/)?.[0] ?? "";
  const sectionDataPathCard = sectionSplitSource.match(/<HtmlWorkflowCard[\s\S]*?title="데이터 경로"[\s\S]*?>/)?.[0] ?? "";
  const downloadDataPathCard = downloadSource.match(/<HtmlWorkflowCard[\s\S]*?title="데이터 경로"[\s\S]*?>/)?.[0] ?? "";

  assert.doesNotMatch(tableDataPathCard, /CardDescription/);
  assert.doesNotMatch(sectionDataPathCard, /description=/);
  assert.doesNotMatch(downloadDataPathCard, /description=/);
  assert.match(templateSource, /description \? "gap-3 pb-4" : "gap-0"/);
});

test("workflow form typography matches standard card fields", async () => {
  const templateSource = await readFile(htmlWorkflowTemplatePath, "utf8");

  assert.match(templateSource, /<CardContent className="space-y-4">/);
  assert.match(templateSource, /<Label className="text-slate-600 dark:text-slate-300">\{label\}<\/Label>/);
  assert.doesNotMatch(templateSource, /<Label className="text-xs font-semibold text-slate-600 dark:text-slate-300">/);
});

test("data path cards keep the same vertical field rhythm across workflow pages", async () => {
  const filterSource = await readFile(filterPagePath, "utf8");
  const utilitySource = await readFile(utilityPagePath, "utf8");
  const assetsSource = await readFile(assetsExcelViewPath, "utf8");

  const filterDataPathCard = filterSource.match(/<Card[\s\S]*?<CardTitle className="dark:text-white">데이터 경로<\/CardTitle>[\s\S]*?<\/Card>/)?.[0] ?? "";
  const utilityPathCard = utilitySource.match(/<Card[\s\S]*?<CardTitle className="dark:text-white">분할저장 구조 전환<\/CardTitle>[\s\S]*?<\/Card>/)?.[0] ?? "";
  const assetsDataPathCard = assetsSource.match(/<Card[\s\S]*?<CardTitle className="dark:text-white">데이터 경로<\/CardTitle>[\s\S]*?<\/Card>/)?.[0] ?? "";

  assert.match(filterDataPathCard, /<CardContent className="grid gap-4">/);
  assert.match(utilityPathCard, /<CardContent className="space-y-4">/);
  assert.doesNotMatch(utilityPathCard, /md:grid-cols-2/);
  assert.match(assetsDataPathCard, /<CardContent className="space-y-4">/);
  assert.doesNotMatch(assetsDataPathCard, /pt-6 space-y-5/);
});

test("graph card typography follows standard card sizing", async () => {
  const graphSources = await Promise.all([
    readFile(graphWorkspacePath, "utf8"),
    readFile(graphNodePath, "utf8"),
    readFile(chartWorkspacePath, "utf8"),
    readFile(analysisWorkspacePath, "utf8"),
  ]);

  for (const source of graphSources) {
    assert.doesNotMatch(source, /<CardTitle[^>]*text-(?:xl|lg)/);
  }

  const chartSource = graphSources[2];
  assert.doesNotMatch(chartSource, /<Label[^>]*text-xs font-semibold text-slate-500/);
});
