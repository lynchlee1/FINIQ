import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlSectionSplitPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
const tablePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx";
const htmlWorkflowTemplatePath = "frontend/finiq_GUI/apps/market-desk/src/components/html-workflow/HtmlWorkflowTemplate.tsx";
const workflowModeSwitchPath = "frontend/finiq_GUI/apps/market-desk/src/components/layout/WorkflowModeSwitch.tsx";
const filterPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx";
const htmlParsePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-parse/page.tsx";
const disclosureAutomationPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-automation/page.tsx";
const disclosureConditionPresetsPath = "frontend/finiq_GUI/apps/market-desk/src/lib/disclosureConditionPresets.ts";
const disclosureConditionCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureConditionFilterCard.tsx";
const jobStreamingHookPath = "frontend/finiq_GUI/apps/market-desk/src/hooks/useJobStreaming.ts";
const utilityPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/utility/page.tsx";
const assetsExcelViewPath = "frontend/finiq_GUI/apps/market-desk/src/features/assets-excel/AssetExcelUtilityView.tsx";
const graphWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyGraphWorkspace.tsx";
const graphNodePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyNodeGraph.tsx";
const chartWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/chart/OntologyChartWorkspace.tsx";
const analysisWorkspacePath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx";
const dataPathCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/data-path/DataPathCard.tsx";
const pathSettingsPath = "frontend/finiq_GUI/apps/market-desk/src/components/data-path/WorkflowPathSettings.tsx";
const webAppFramePath = "frontend/finiq_GUI/packages/web-app/src/components/layout/AppFrame.tsx";
const marketDeskGlobalsPath = "frontend/finiq_GUI/apps/market-desk/src/app/globals.css";

test("streamed disclosure filtering reports ten-second progress silence", async () => {
  const source = await readFile(jobStreamingHookPath, "utf8");

  assert.match(source, /event\.type === "heartbeat"/);
  assert.match(source, /작업 스레드 실행 중/);
  assert.match(source, /새 진행 \$\{formatElapsed\(progressIdleSeconds\)\}째 없음/);
});

test("html section split path fields stack vertically", async () => {
  const source = await readFile(htmlSectionSplitPath, "utf8");
  const pathFieldsBlock = source.match(/const folderPathFields: DataPathField\[\][\s\S]*?\n  \];/)?.[0] ?? "";

  assert.match(pathFieldsBlock, /id: "inputDirectory"/);
  assert.match(pathFieldsBlock, /id: "outputDirectory"[\s\S]*?separateOutputOnly: true/);
});

test("html section split uses shared data path and execution cards", async () => {
  const source = await readFile(htmlSectionSplitPath, "utf8");
  const resultsSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx",
    "utf8",
  );
  const combinedSource = `${source}\n${resultsSource}`;

  assert.match(source, /pathFields=\{folderPathFields\}/);
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
  assert.match(source, /const workerCount = Number\(config\.parallel_worker_count\)/);
  assert.match(source, /setWorkers\(String\(workerCount\)\)/);
  assert.doesNotMatch(source, /config\.parallel_worker_count \|\| 1/);
  assert.match(source, /label: SETTINGS_LABELS\.workerCount/);
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
  const pathFields = pageSource.match(/const folderPathFields: DataPathField\[\][\s\S]*?\n  \];/)?.[0] ?? "";
  assert.doesNotMatch(pathFields, /disabled:/);
  assert.match(pathFields, /label: DATA_PATH_LABELS\.workspace/);
  assert.match(pathFields, /onChange: handleWorkspaceDirectoryChange/);
  assert.match(pathFields, /separateOutputOnly: true/);
  assert.match(pathFields, /onChange: handleOutputDirectoryChange/);
  assert.match(pageSource, /data_root: dataRoot/);
  assert.match(pageSource, /html_parse_mode: htmlParseMode/);
  assert.match(pageSource, /mode: htmlParseMode/);
  assert.match(resultsSource, /WorkflowPathSettings id="section-split-separate-output-directory"/);
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
  const pathSettingsSource = await readFile(pathSettingsPath, "utf8");
  assert.match(downloadSource, /value: dataRoot,\s*onChange: \(val\) => saveSetting\("output_root", val\)/);
  assert.doesNotMatch(pathSettingsSource, /저장 디렉토리 별도 설정하기/);
  assert.doesNotMatch(pathSettingsSource, /saveSetting\("disclosure_separate_output_directory"/);
  assert.doesNotMatch(templateSource, /disabled=\{field\.disabled\}/);
  assert.match(tableSource, /value: dataRoot/);
  assert.match(tableSource, /separateOutputOnly: true/);
  assert.match(tableSource, /root_directory: useSeparateOutputDirectory/);
  assert.match(tableSource, /saveSetting\("sqlite_output_directory", val\)/);
  assert.doesNotMatch(filterSource, /classification_path:/);
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
    assert.match(source, /작업공간 디렉토리|DATA_PATH_LABELS\.workspace/);
    assert.match(source, /WorkflowPathSettings/);
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
  const dataPathCardSource = await readFile(dataPathCardPath, "utf8");

  assert.match(source, /<DataPathCard/);
  assert.doesNotMatch(source, /<div className="grid gap-4 md:grid-cols-2">/);
  assert.match(dataPathCardSource, /span=\{4\}/);
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

  const tableDataPathCard = tableSource.match(/<WorkflowPathSettings[^>]*\/>/)?.[0] ?? "";
  const sectionDataPathCard = sectionSplitSource.match(/<HtmlWorkflowCard[\s\S]*?title="데이터 경로"[\s\S]*?>/)?.[0] ?? "";
  const downloadDataPathCard = downloadSource.match(/<HtmlWorkflowCard[\s\S]*?title="데이터 경로"[\s\S]*?>/)?.[0] ?? "";

  assert.ok(tableDataPathCard, "표 변환 페이지는 공용 경로 설정을 써야 합니다.");
  assert.doesNotMatch(tableDataPathCard, /description=/);
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

test("right-dock number settings use compact inspector rows", async () => {
  const templateSource = await readFile(htmlWorkflowTemplatePath, "utf8");
  const downloadSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx",
    "utf8",
  );
  const htmlDownloadSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx",
    "utf8",
  );
  const parseSource = await readFile(htmlParsePagePath, "utf8");
  const sectionResultsSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx",
    "utf8",
  );

  const settingsLabelsSource = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/config/uiText.ts",
    "utf8",
  );
  assert.match(settingsLabelsSource, /workerCount: "워커 수"/);
  assert.match(settingsLabelsSource, /timeoutSeconds: "타임아웃 \(초\)"/);
  assert.match(settingsLabelsSource, /requestIntervalSeconds: "요청 간격 \(초\)"/);
  assert.match(templateSource, /htmlSelectValueClassName = "min-w-0 flex-1 truncate text-left"/);
  assert.match(templateSource, /htmlSelectItemClassName = "whitespace-nowrap"/);
  assert.match(templateSource, /export function HtmlInspectorField/);
  assert.match(templateSource, /export function HtmlInspectorToggle/);
  assert.match(templateSource, /layout === "inspector" && field\.kind === "input" && field\.type === "number"/);
  assert.match(templateSource, /htmlInspectorControlClassName/);
  assert.match(templateSource, /variant=\{checked \? "default" : "outline"\}/);
  assert.match(templateSource, /justify-start px-3/);
  assert.match(templateSource, /text-\[var\(--tv-accent-foreground\)\]/);
  assert.match(templateSource, /\{checked \? "On" : "Off"\}/);
  assert.match(templateSource, /HtmlInspectorField label=\{field\.checkboxLabel\}/);
  assert.match(downloadSource, /<HtmlInspectorField label=\{SETTINGS_LABELS\.pageSize\}>/);
  assert.match(downloadSource, /<HtmlInspectorField label=\{SETTINGS_LABELS\.timeoutSeconds\}>/);
  assert.match(downloadSource, /<HtmlInspectorField label=\{SETTINGS_LABELS\.parallelStrategy\}>/);
  assert.match(downloadSource, /label: "한 연도 내 병렬"/);
  assert.match(downloadSource, /label: "연도별 병렬"/);
  assert.match(templateSource, /htmlInspectorSelectClassName/);
  assert.match(templateSource, /if \(field\.kind === "select"\) \{[\s\S]*?if \(layout === "inspector"\)/);
  assert.doesNotMatch(downloadSource, /같은 워커 수를 연도 간/);
  assert.match(htmlDownloadSource, /HtmlWorkflowForm layout="inspector" fields=\{requestOptionFields\}/);
  assert.match(parseSource, /HtmlWorkflowForm layout="inspector" fields=\{parseOptionFields\}/);
  assert.match(sectionResultsSource, /HtmlWorkflowForm layout="inspector" fields=\{settingsFields\}/);
});

test("data path cards keep the same vertical field rhythm across workflow pages", async () => {
  const sources = await Promise.all([
    readFile(filterPagePath, "utf8"),
    readFile(tablePagePath, "utf8"),
    readFile(utilityPagePath, "utf8"),
    readFile(assetsExcelViewPath, "utf8"),
    readFile(htmlParsePagePath, "utf8"),
    readFile(htmlSectionSplitPath, "utf8"),
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(
      "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx",
      "utf8",
    ),
  ]);
  const dataPathCardSource = await readFile(dataPathCardPath, "utf8");
  const pathSettingsSource = await readFile(pathSettingsPath, "utf8");

  for (const source of sources) {
    assert.match(source, /import \{[^}]*DataPathField[^}]*\} from "@\/components\/data-path\/DataPathCard"/);
    assert.doesNotMatch(source, /<PathPickerInput/);
    assert.match(source, /LEGACY: 본문 데이터 경로 카드/);
    assert.doesNotMatch(source.replace(/\{\/\*[\s\S]*?\*\/\}/g, ""), /<DataPathCard/);
  }
  assert.match(dataPathCardSource, /export const DATA_PATH_LABEL = "작업공간 디렉토리"/);
  assert.match(dataPathCardSource, /workspace: DATA_PATH_LABEL/);
  assert.match(dataPathCardSource, /input: DATA_PATH_LABEL/);
  assert.match(dataPathCardSource, /output: DATA_PATH_LABEL/);
  assert.doesNotMatch(dataPathCardSource, /입력 데이터 경로/);
  assert.doesNotMatch(dataPathCardSource, /결과 데이터 경로/);
  assert.match(dataPathCardSource, /LEGACY: 본문에 놓던 데이터 경로 카드/);
  assert.match(pathSettingsSource, /const inputFields = fields\.filter\(\(field\) => !field\.separateOutputOnly\)/);
  assert.doesNotMatch(pathSettingsSource, /저장 디렉토리 별도 설정하기/);
  assert.doesNotMatch(pathSettingsSource, /useSeparateOutputDirectory && outputFields\.map/);
  assert.doesNotMatch(dataPathCardSource, /disclosure_separate_output_directory/);
});

test("disclosure filter workspace picker selects a folder", async () => {
  const source = await readFile(filterPagePath, "utf8");
  const dataPathCardSource = await readFile(dataPathCardPath, "utf8");
  const workspaceField = source.match(/id: "workspace",[\s\S]*?\},/)?.[0] ?? "";

  assert.match(workspaceField, /label: DATA_PATH_LABELS\.workspace/);
  assert.doesNotMatch(workspaceField, /mode:/);
  assert.match(dataPathCardSource, /mode=\{field\.mode \|\| "folder"\}/);
});

test("disclosure filter removes the parser mode from the data path card", async () => {
  const source = await readFile(filterPagePath, "utf8");
  const dataPathCard = source.match(/<DataPathCard[\s\S]*?\n {10}\/>/)?.[0] ?? "";

  assert.ok(dataPathCard, "필터 페이지는 공용 데이터 경로 카드를 써야 합니다.");
  assert.match(source, /const \[mode, setMode\] = useState\(""\)/);
  assert.match(source, /data_root: rootDirectory,\s*mode: selectedPreset\.trim\(\) \|\| mode,/);
  assert.doesNotMatch(source, /workflow_name/);
  assert.match(source, /const filterMode = selectedPreset\.trim\(\) \|\| mode;/);
  assert.match(source, /if \(!filterMode\) \{[\s\S]*?조건검색 필터를 선택하세요/);
  assert.doesNotMatch(dataPathCard, /파싱 모드/);
  assert.doesNotMatch(dataPathCard, /<select/);
});

test("disclosure filter initializes counts to 1000 and submits them without fallback", async () => {
  const source = await readFile(filterPagePath, "utf8");

  assert.match(source, /const \[limit, setLimit\] = useState\("1000"\)/);
  assert.match(source, /const \[progressInterval, setProgressInterval\] = useState\("1000"\)/);
  assert.match(source, /progress_interval: configuredProgressInterval/);
  assert.doesNotMatch(source, /Number\(progressInterval \|\| 1000\)/);
});

test("disclosure filter auto-loads workspace JSON presets without a load button", async () => {
  const source = await readFile(filterPagePath, "utf8");
  const conditionCardSource = await readFile(disclosureConditionCardPath, "utf8");

  assert.match(source, /listDisclosureConditionPresets\(rootDirectory\)/);
  assert.doesNotMatch(source, /pickPath/);
  assert.doesNotMatch(source, /\/api\/disclosures\/filter\/preset(?:["/])/);
  assert.doesNotMatch(source, /onLoadPresetFromJson/);
  assert.match(conditionCardSource, /onLoadPresetFromJson\?: \(\) => void/);
  assert.match(conditionCardSource, /\{onLoadPresetFromJson && <Button variant="outline" onClick=\{onLoadPresetFromJson\}>/);
  assert.match(conditionCardSource, /role="combobox"/);
  assert.match(conditionCardSource, /placeholder="필터 선택"/);
  assert.match(conditionCardSource, /onSelectExisting=\{onLoadPreset\}/);
  assert.match(conditionCardSource, /\{value\.trim\(\)\} 새 필터/);
  assert.doesNotMatch(conditionCardSource, /workflowStatusLabel/);
  assert.doesNotMatch(conditionCardSource, /placeholder="프리셋 이름"/);
  assert.match(conditionCardSource, /onClick=\{onSavePreset\}/);
  assert.doesNotMatch(conditionCardSource, /onRenamePreset/);
  assert.match(conditionCardSource, /onClick=\{onDeletePreset\} disabled=\{!presets\.some\(\(preset\) => preset\.name === selectedPreset\)\}/);
  assert.match(conditionCardSource, /DisclosureFilterConnector = "" \| "AND" \| "XOR" \| "OR"/);
  assert.match(conditionCardSource, /<option value="XOR">XOR<\/option>/);
  assert.match(conditionCardSource, /mixed condition block connectors must be separated by parentheses/);
});

test("disclosure condition card keeps operators scoped to each field type", async () => {
  const source = await readFile(disclosureConditionCardPath, "utf8");
  const operatorBlock = (name) => {
    const match = source.match(new RegExp(`const ${name} = \\[([\\s\\S]*?)\\] as const`));
    assert.ok(match, `${name} 목록이 있어야 합니다.`);
    return match[1];
  };

  assert.match(source, /export const DISCLOSURE_FILTER_FIELD_OPERATORS/);
  assert.match(source, /operatorsForField\(condition\.field\)/);
  assert.match(source, /defaultOperatorForField\(field\)/);
  assert.match(source, /badges: DISCLOSURE_FILTER_SET_OPERATORS/);
  assert.match(source, /disclosed_date: DISCLOSURE_FILTER_DATE_OPERATORS/);
  assert.match(source, /market: DISCLOSURE_FILTER_ENUM_OPERATORS/);
  assert.match(operatorBlock("DISCLOSURE_FILTER_SET_OPERATORS"), /"contains"/);
  assert.doesNotMatch(operatorBlock("DISCLOSURE_FILTER_SET_OPERATORS"), /on_or_before/);
  assert.doesNotMatch(operatorBlock("DISCLOSURE_FILTER_ENUM_OPERATORS"), /on_or_before/);
  assert.doesNotMatch(operatorBlock("DISCLOSURE_FILTER_TEXT_OPERATORS"), /on_or_before/);
  assert.match(operatorBlock("DISCLOSURE_FILTER_DATE_OPERATORS"), /on_or_before/);
});

test("disclosure condition card documents each filter field with a stored example", async () => {
  const source = await readFile(disclosureConditionCardPath, "utf8");

  assert.match(source, /aria-label="필드 설명"/);
  assert.match(source, /<CircleHelp className="h-4 w-4" \/>/);
  assert.match(source, /DISCLOSURE_FILTER_MARKET_VALUES = \["유가증권", "코스닥", "코넥스"\]/);
  assert.match(source, /\["badges", "배지"\]/);
  assert.match(source, /공시 제목입니다\./);
  assert.match(source, /기업명입니다\./);
  assert.match(source, /제출인 이름입니다\./);
  assert.match(source, /상장된 시장입니다\./);
  assert.match(source, /KIND 회사 아이콘 배지입니다\./);
  assert.match(source, /공시된 날짜입니다\. \(YYYY-MM-DD 형식\)/);
  assert.match(source, /공시의 접수번호입니다\. \(YYYYMMDDXXXXXX 형식\)/);
  assert.match(source, /KIND 내부 회사 분류 코드입니다\./);
  assert.doesNotMatch(source, /아니라/);
  for (const example of [
    "주주총회소집결의",
    "[정정]단일판매ㆍ공급계약체결",
    "삼성전자",
    "SK하이닉스",
    "알테오젠",
    "유가증권",
    "코스닥",
    "코넥스",
    "상장폐지",
    "관리종목",
    "KOSPI200",
    "2026-01-02",
    "20251231000708",
    "19960103M00001",
    "00593",
    "0126Z",
    "USA12",
  ]) {
    assert.match(source, new RegExp(example.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("disclosure condition card places an undoable clear button between undo and redo", async () => {
  const source = await readFile(disclosureConditionCardPath, "utf8");
  const undoIndex = source.indexOf('aria-label="실행 취소"');
  const clearIndex = source.indexOf('aria-label="지우기"');
  const redoIndex = source.indexOf('aria-label="다시 실행"');

  assert.ok(undoIndex >= 0, "실행 취소 버튼이 있어야 합니다.");
  assert.ok(clearIndex > undoIndex && redoIndex > clearIndex, "지우기 버튼은 실행 취소와 다시 실행 사이에 있어야 합니다.");
  assert.match(source, /const clear = \(\) => \{[\s\S]*?applyConditionsChange\(\[makeEmptyDisclosureCondition\(\)\]\)/);
  assert.match(source, /disabled=\{isEmptyDisclosureConditionBlocks\(conditions\)\}/);
});

test("disclosure condition card uses slate text in dark mode", async () => {
  const [conditionCardSource, filterPageSource, candidateCardSource] = await Promise.all([
    readFile(disclosureConditionCardPath, "utf8"),
    readFile(filterPagePath, "utf8"),
    readFile("frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureFilterCandidateCard.tsx", "utf8"),
  ]);

  assert.doesNotMatch(conditionCardSource, /(?:text|bg|border)-(?:teal|cyan)-/);
  assert.doesNotMatch(filterPageSource, /(?:text|bg|border)-(?:teal|cyan)-/);
  assert.doesNotMatch(candidateCardSource, /(?:text|bg|border)-(?:teal|cyan)-/);
  assert.match(conditionCardSource, /dark:text-slate-200/);
});

test("disclosure filter page combines title search and recorded filtering", async () => {
  const [source, webAppFrameSource, globalsSource, modeSwitchSource] = await Promise.all([
    readFile(filterPagePath, "utf8"),
    readFile(webAppFramePath, "utf8"),
    readFile(marketDeskGlobalsPath, "utf8"),
    readFile(workflowModeSwitchPath, "utf8"),
  ]);

  assert.match(source, /<DisclosureConditionFilterCard/);
  assert.match(source, /listDisclosureConditionPresets\(rootDirectory\)/);
  assert.match(source, /type FilterTaskMode = "title-search" \| "filter"/);
  assert.match(source, /const \[taskMode, setTaskMode\] = useState<FilterTaskMode>\("title-search"\)/);
  assert.match(source, /\{ value: "title-search", label: "공시내역 제목 검색", icon: Search \}/);
  assert.match(source, /\{ value: "filter", label: "공시내역 필터링", icon: Filter \}/);
  assert.ok(
    source.indexOf("<DisclosureConditionFilterCard")
      < source.indexOf("<WorkflowModeSwitch")
      && source.indexOf("<WorkflowModeSwitch")
        < source.indexOf('<CardTitle className="dark:text-white">작업 실행</CardTitle>'),
    "동작 전환은 공통 카드 아래, 작업 실행 카드 바로 위의 독립 행이어야 합니다.",
  );
  assert.match(source, /ariaLabel="공시 작업 모드"/);
  assert.match(source, /options=\{FILTER_TASK_MODE_OPTIONS\}/);
  assert.match(source, /onValueChange=\{setTaskMode\}/);
  assert.match(source, /testId="filter-mode-control"/);
  assert.match(modeSwitchSource, /role="group"\s+aria-label=\{ariaLabel\}/);
  assert.match(modeSwitchSource, /aria-pressed=\{selected\}/);
  assert.match(source, /useJobPolling/);
  assert.match(source, /pollingEndpoint: "\/api\/disclosures\/titles\/jobs\/\{jobId\}"/);
  assert.match(source, /"\/api\/disclosures\/titles\/search\/start"/);
  assert.match(source, /startTitlePolling\(response\.job_id\)/);
  assert.match(source, /if \(titleJobId\) \{\s*setTaskMode\("title-search"\)/);
  assert.match(source, /const activeStatusMode: FilterTaskMode = titleJobId[\s\S]*?isStreaming[\s\S]*?taskMode/);
  assert.match(source, /streamJob\("\/api\/disclosures\/filter"/);
  assert.doesNotMatch(source, /taskMode === "title-search" \? "검색" : "실행"/);
  assert.match(source, /\n\s+실행\n/);
  assert.match(source, /<ActionDock/);
  assert.match(source, /<JobStatusLogger/);
  assert.match(webAppFrameSource, /overflow-x-clip/);
  assert.doesNotMatch(webAppFrameSource, /overflow-x-hidden/);
  assert.match(globalsSource, /html, body \{[\s\S]*?overflow-x: clip;/);
  assert.doesNotMatch(globalsSource, /html, body \{[\s\S]*?overflow-x: hidden;/);
  assert.match(source, /data_root: rootDirectory/);
  assert.match(source, /filter_blocks: normalizeDisclosureConditionBlocks\(conditions\)/);
  assert.match(source, /<CardTitle className="dark:text-white">제목 검색 결과<\/CardTitle>/);
  assert.match(source, /<CardTitle className="dark:text-white">필터 결과<\/CardTitle>/);
});

test("disclosure mode controls use a transparent compact row near the workflow cards", async () => {
  const [modeSwitchSource, templateSource, filterSource, htmlDownloadSource] = await Promise.all([
    readFile(workflowModeSwitchPath, "utf8"),
    readFile(htmlWorkflowTemplatePath, "utf8"),
    readFile(filterPagePath, "utf8"),
    readFile(
      "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx",
      "utf8",
    ),
  ]);

  assert.match(modeSwitchSource, /<div className="space-y-3">/);
  assert.match(modeSwitchSource, /className="inline-flex w-full gap-1 rounded-md border border-\[color:var\(--tv-border\)\] p-1 sm:w-auto"/);
  assert.match(modeSwitchSource, /className="h-8 flex-1 gap-1 px-2 duration-150 sm:flex-none"/);
  assert.match(templateSource, /return <WorkflowModeSwitch \{\.\.\.modeSwitch\}>\{children\}<\/WorkflowModeSwitch>/);
  assert.match(filterSource, /<WorkflowModeSwitch[\s\S]*?options=\{FILTER_TASK_MODE_OPTIONS\}/);
  assert.match(htmlDownloadSource, /\{variant === "external" && \(\s*<WorkflowModeSwitch/);
  assert.match(htmlDownloadSource, /options=\{EXTERNAL_TASK_MODE_OPTIONS\}/);
  assert.ok(
    htmlDownloadSource.indexOf("<WorkflowModeSwitch")
      < htmlDownloadSource.indexOf('<CardTitle className="dark:text-white">작업 실행</CardTitle>'),
    "외부 HTML 모드 전환도 작업 실행 카드 바로 위의 독립 행이어야 합니다.",
  );
  for (const source of [filterSource, htmlDownloadSource]) {
    assert.doesNotMatch(source, /inline-flex .*border-\[color:var\(--tv-border\)\].*p-1/);
  }
});

test("disclosure filter inspection checks every folder without a selected filter", async () => {
  const source = await readFile(filterPagePath, "utf8");
  const handler = source.slice(
    source.indexOf("const handleInspectExistingFilter"),
    source.indexOf("if (loading)", source.indexOf("const handleInspectExistingFilter")),
  );

  assert.match(handler, /action: "inspect"/);
  assert.match(handler, /data_root: dataRoot/);
  assert.match(handler, /response\.presets\s*\.filter\(\(preset\) => preset\.status !== "completed"\)/);
  assert.match(handler, /isCurrentPresetWorkspace\(dataRoot, requestId\)/);
  assert.doesNotMatch(handler, /selectedPreset|selectedWorkflow|condition_blocks/);
  assert.match(source, /title: "조건검색 폴더 전체 검사"/);
});

test("disclosure automation exposes filter presets for every dependent stage range", async () => {
  const source = await readFile(disclosureAutomationPagePath, "utf8");

  assert.match(source, /const filterSettingsSelected = executionMask\.some\(\(stage\) => stage >= 3\)/);
  assert.match(source, /executionMask\.some\(\(stage\) => stage >= 3\) && !selectedPreset/);
});

test("disclosure filter keeps workflow status scoped to the active workspace", async () => {
  const source = await readFile(filterPagePath, "utf8");
  const streamingSource = await readFile(jobStreamingHookPath, "utf8");

  assert.match(source, /const presetListRequestIdRef = useRef\(0\)/);
  assert.match(source, /currentDataRootRef\.current = rootDirectory/);
  assert.match(source, /setSelectedPreset\(""\)/);
  assert.match(source, /if \(requestId !== presetListRequestIdRef\.current\) return/);
  assert.match(source, /const isCurrentPresetWorkspace = \(dataRoot: string, requestId: number\)/);
  assert.ok(
    (source.match(/if \(!isCurrentPresetWorkspace\(dataRoot, requestId\)\) return;/g) || []).length >= 6,
    "모든 비동기 프리셋 응답은 현재 작업공간에만 적용해야 합니다.",
  );
  assert.match(source, /const filterMode = selectedPreset\.trim\(\) \|\| mode;/);
  assert.match(source, /status: "running"/);
  assert.match(source, /streamOutcome === "aborted"/);
  assert.match(source, /workflow\?\.status !== "running"/);
  assert.match(streamingSource, /return "aborted"/);
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
    assert.doesNotMatch(source, /renameDisclosureConditionPreset/);
    assert.match(source, /deleteDisclosureConditionPreset/);
    assert.doesNotMatch(source, /condition_presets/);
    assert.doesNotMatch(source, /saveSetting\("condition_presets"/);
  }

  const storeSource = await readFile(disclosureConditionPresetsPath, "utf8");
  assert.match(storeSource, /const endpoint = "\/api\/disclosures\/filter\/presets"/);
  assert.match(storeSource, /data_root: dataRoot, action: "list"/);
  assert.match(storeSource, /data_root: dataRoot, action: "save", preset/);
  assert.doesNotMatch(storeSource, /action: "rename"/);
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
