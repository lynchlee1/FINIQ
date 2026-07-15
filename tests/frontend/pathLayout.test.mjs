import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlSectionSplitPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
const tablePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx";
const htmlWorkflowTemplatePath = "frontend/finiq_GUI/apps/market-desk/src/components/html-workflow/HtmlWorkflowTemplate.tsx";
const filterPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx";
const htmlParsePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-parse/page.tsx";
const disclosureAutomationPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-automation/page.tsx";
const disclosureConditionPresetsPath = "frontend/finiq_GUI/apps/market-desk/src/lib/disclosureConditionPresets.ts";
const disclosureConditionCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureConditionFilterCard.tsx";
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
  const resultsSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx",
    "utf8",
  );
  const combinedSource = `${source}\n${resultsSource}`;

  assert.match(source, /title="데이터 경로"/);
  assert.match(source, /title="작업 실행"/);
  assert.match(combinedSource, /소스 불러오기/);
  assert.match(combinedSource, /FolderOpen/);
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

test("html section split exposes worker count setting and background section kind job", async () => {
  const source = await readFile(htmlSectionSplitPath, "utf8");

  assert.match(source, /const \[workers, setWorkers\] = useState\("1"\)/);
  assert.match(source, /setWorkers\(String\(config\.parallel_worker_count \|\| 1\)\)/);
  assert.match(source, /label: "병렬 처리 개수"/);
  assert.match(source, /\/api\/disclosures\/html\/sections\/kinds\/start/);
  assert.match(source, /workers: parseOptionalNumber\(workers\)/);
  assert.match(source, /\/api\/disclosures\/html\/cancel/);
  assert.match(source, /setSectionPatterns\(items\)/);
});

test("html section split can cancel save jobs and source loading", async () => {
  const pageSource = await readFile(htmlSectionSplitPath, "utf8");
  const resultsSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx",
    "utf8",
  );

  assert.match(pageSource, /onClick=\{cancelInspectFolder\} disabled=\{!isInspecting && !isJobActive\}/);
  assert.match(pageSource, /activeJobIdRef\.current = activeJobId/);
  assert.match(pageSource, /body: JSON\.stringify\(\{ job_id: activeJobIdRef\.current \}\)/);
  assert.match(resultsSource, /isCancellable=\{isJobActive \|\| isInspecting\}/);
});

test("html section split keeps workspace paths directly editable", async () => {
  const pageSource = await readFile(htmlSectionSplitPath, "utf8");
  const resultsSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx",
    "utf8",
  );
  const storeSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/store/useSettingsStore.ts",
    "utf8",
  );

  assert.match(storeSource, /html_section_split_output_directory: string/);
  assert.match(storeSource, /disclosure_separate_output_directory: boolean/);
  assert.match(storeSource, /disclosure_separate_output_directory: false/);
  assert.match(pageSource, /disclosure_separate_output_directory: useSeparateOutputDirectory/);
  assert.match(pageSource, /setOutputDirectory\(config\.html_section_split_output_directory \|\| ""\)/);
  assert.doesNotMatch(pageSource, /`\$\{defaultInput\}_sections`/);
  const pathFields = pageSource.match(/const folderPathFields:[\s\S]*?const splitOptionFields:/)?.[0] ?? "";
  assert.doesNotMatch(pathFields, /disabled:/);
  assert.match(pathFields, /label: "작업공간 디렉토리"/);
  assert.match(pathFields, /onChange: handleWorkspaceDirectoryChange/);
  assert.match(pathFields, /\.\.\.\(useSeparateOutputDirectory \? \[\{/);
  assert.match(pathFields, /onChange: handleOutputDirectoryChange/);
  assert.match(pageSource, /data_root: dataRoot/);
  assert.match(resultsSource, /DisclosureSeparateOutputDirectorySetting id="section-split-separate-output-directory"/);
});

test("disclosure detail pages share one workspace and hide separate outputs by default", async () => {
  const downloadSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx",
    "utf8",
  );
  const tableSource = await readFile(tablePagePath, "utf8");
  const filterSource = await readFile(filterPagePath, "utf8");
  const htmlDownloadSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx",
    "utf8",
  );
  const parseSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-parse/page.tsx",
    "utf8",
  );
  const templateSource = await readFile(htmlWorkflowTemplatePath, "utf8");
  const separateSettingSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureSeparateOutputDirectorySetting.tsx",
    "utf8",
  );
  assert.match(downloadSource, /value=\{dataRoot\}[\s\S]*?onChange=\{\(val\) => saveSetting\("output_root", val\)\}/);
  assert.match(separateSettingSource, /저장 디렉토리 별도 설정하기/);
  assert.match(separateSettingSource, /saveSetting\("disclosure_separate_output_directory", !!value\)/);
  assert.doesNotMatch(templateSource, /disabled=\{field\.disabled\}/);
  assert.match(tableSource, /value=\{dataRoot\}/);
  assert.match(tableSource, /useSeparateOutputDirectory && <div/);
  assert.match(tableSource, /root_directory: useSeparateOutputDirectory/);
  assert.match(tableSource, /saveSetting\("sqlite_output_directory", val\)/);
  assert.match(filterSource, /\.\.\.\(useSeparateOutputDirectory[\s\S]*?classification_path:/);
  assert.match(filterSource, /saveSetting\("external_html_transfer_directory", val\)/);
  assert.doesNotMatch(filterSource, /saveSetting\("external_html_transfer_directory", transferPath\)/);
  const sourcePayload = htmlDownloadSource.match(/const sourcePayload[\s\S]*?const currentSourcePath/)?.[0] ?? "";
  assert.match(sourcePayload, /if \(variant === "external"\) \{[\s\S]*?return \{\};/);
  assert.doesNotMatch(sourcePayload, /source_json_path/);
  assert.doesNotMatch(htmlDownloadSource, /finiq\.kind\.filteredDisclosures/);
  assert.match(htmlDownloadSource, /output_directory: useSeparateOutputDirectory \? outputDirectory : ""/);
  assert.match(parseSource, /input_directory: useSeparateOutputDirectory \? inputDirectory : ""/);
  for (const source of [downloadSource, tableSource, filterSource, htmlDownloadSource, parseSource]) {
    assert.doesNotMatch(source, /disabled: true/);
    assert.match(source, /작업공간 디렉토리/);
    assert.match(source, /DisclosureSeparateOutputDirectorySetting/);
  }
  for (const source of [downloadSource, tableSource, filterSource, htmlDownloadSource, parseSource]) {
    assert.match(source, /data_root:/);
  }
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
    "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx",
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
  assert.match(templateSource, /<Label className="text-body text-\[var\(--tv-text\)\]">\{label\}<\/Label>/);
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

test("disclosure filter workspace picker selects a folder", async () => {
  const source = await readFile(filterPagePath, "utf8");
  const workspacePicker = source.match(/<Label[^>]*>작업공간 디렉토리<\/Label>[\s\S]*?<PathPickerInput[\s\S]*?\/>/)?.[0] ?? "";

  assert.match(workspacePicker, /mode="folder"/);
  assert.doesNotMatch(workspacePicker, /mode="save"/);
});

test("disclosure filter requires a parser mode for mode-folder output", async () => {
  const source = await readFile(filterPagePath, "utf8");

  assert.match(source, /const \[mode, setMode\] = useState\(""\)/);
  assert.match(source, /mode,\s*\.\.\.\(useSeparateOutputDirectory/);
  assert.match(source, /if \(!mode\) \{[\s\S]*?파싱 모드를 선택하세요/);
  assert.match(source, /\{ key: "bond_issuance", label: "사채발행파싱" \}/);
  assert.match(source, /\{ key: "rights_issuance", label: "유무상증자파싱" \}/);
  assert.match(source, /\{ key: "shareholder_meeting", label: "주주총회파싱" \}/);
  assert.match(source, /saveSetting\("html_parse_mode", event\.target\.value\)/);
});

test("disclosure filter defaults processing, return, and progress counts to 1000", async () => {
  const source = await readFile(filterPagePath, "utf8");

  assert.match(source, /const \[limit, setLimit\] = useState\("1000"\)/);
  assert.match(source, /const \[progressInterval, setProgressInterval\] = useState\("1000"\)/);
  assert.match(source, /progress_interval: Number\(progressInterval \|\| 1000\)/);
});

test("disclosure filter loads saved JSON filters and auto-applies selected presets", async () => {
  const source = await readFile(filterPagePath, "utf8");
  const conditionCardSource = await readFile(disclosureConditionCardPath, "utf8");

  assert.match(source, /pickPath\(\{[\s\S]*?title: "필터 결과 JSON 선택"/);
  assert.match(source, /apiPost<DisclosureConditionPresetPayload>\("\/api\/disclosures\/filter\/preset"/);
  assert.match(source, /source_json_path: sourceJsonPath/);
  assert.match(source, /onLoadPresetFromJson=\{loadFilterPresetFromJson\}/);
  assert.match(conditionCardSource, /<Button variant="outline" onClick=\{onLoadPresetFromJson\}>[\s\S]*?<Upload className="mr-2 h-4 w-4" \/>불러오기<\/Button>/);
  assert.match(conditionCardSource, /onClick=\{onRenamePreset\} disabled=\{!selectedPreset\}/);
  assert.match(conditionCardSource, /\/>수정<\/Button>/);
  assert.match(conditionCardSource, /if \(nextPreset\) onLoadPreset\(nextPreset\)/);
  assert.doesNotMatch(source, /<Label className="dark:text-slate-300">필터 결과 JSON<\/Label>/);
  assert.doesNotMatch(source, /onClick=\{loadPreset\} disabled=\{!selectedPreset\}>불러오기/);
});

test("disclosure condition presets use only the workspace JSON store", async () => {
  const sources = await Promise.all([
    readFile(filterPagePath, "utf8"),
    readFile(htmlParsePagePath, "utf8"),
    readFile(disclosureAutomationPagePath, "utf8"),
  ]);

  for (const source of sources) {
    assert.match(source, /listDisclosureConditionPresets/);
    assert.match(source, /saveDisclosureConditionPreset/);
    assert.match(source, /renameDisclosureConditionPreset/);
    assert.match(source, /deleteDisclosureConditionPreset/);
    assert.doesNotMatch(source, /condition_presets/);
    assert.doesNotMatch(source, /saveSetting\("condition_presets"/);
  }

  const storeSource = await readFile(disclosureConditionPresetsPath, "utf8");
  assert.match(storeSource, /const endpoint = "\/api\/disclosures\/filter\/presets"/);
  assert.match(storeSource, /data_root: dataRoot, action: "list"/);
  assert.match(storeSource, /data_root: dataRoot, action: "save", preset/);
  assert.match(storeSource, /action: "rename"/);
  assert.match(storeSource, /action: "delete"/);
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
