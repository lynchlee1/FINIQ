import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const pagePath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/app/html-parse/page.tsx");
const candidateCardPath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureFilterCandidateCard.tsx");

test("html parse page does not render warning or step guide boxes", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.doesNotMatch(source, /새 양식에서 필드가 비면 warnings와 원본 HTML을 함께 확인하세요/);
  assert.doesNotMatch(source, /title: "1\. HTML 폴더 선택"/);
  assert.doesNotMatch(source, /<HtmlStepGuide/);
  assert.doesNotMatch(source, /title="작동 원리와 파싱 방식"/);
  assert.doesNotMatch(source, /PARSING_RULES/);
  assert.doesNotMatch(source, /Label className="dark:text-slate-300">파싱 경고/);
  assert.match(source, /notificationActive=\{isErrorStatus \|\| !!executionOptionExampleNotice \|\| warningReports\.length > 0\}/);
});

test("html parse page uses standard two-row data path card", async () => {
  const source = await readFile(pagePath, "utf8");
  const pathFieldsBlock = source.match(/const parsePathFields: DataPathField\[\][\s\S]*?\n  \];/)?.[0] ?? "";
  const dataPathCard = source.match(/<DataPathCard[\s\S]*?\/>/)?.[0] ?? "";

  assert.match(pathFieldsBlock, /id: "inputDirectory"/);
  assert.match(pathFieldsBlock, /id: "outputDirectory"[\s\S]*?separateOutputOnly: true/);
  assert.match(source, /WorkflowPathSettings id="parse-separate-output-directory"/);
  assert.doesNotMatch(source, /title="공시원문 변환 경로"/);
  assert.doesNotMatch(dataPathCard, /description=/);
});

test("html parse page keeps workspace directories directly editable", async () => {
  const source = await readFile(pagePath, "utf8");
  const pathFields = source.match(/const parsePathFields: DataPathField\[\][\s\S]*?\n  \];/)?.[0] ?? "";
  const modeHandler = source.match(/const handleModeChange =[\s\S]*?\n  };/)?.[0] ?? "";

  assert.doesNotMatch(pathFields, /disabled:/);
  assert.match(pathFields, /label: DATA_PATH_LABELS\.workspace/);
  assert.match(pathFields, /onChange: handleWorkspaceDirectoryChange/);
  assert.match(pathFields, /separateOutputOnly: true/);
  assert.match(pathFields, /onChange: handleOutputDirectoryChange/);
  assert.match(source, /data_root: dataRoot/);
  assert.match(source, /setInputDirectory\(config\.html_section_split_output_directory \|\| ""\)/);
  assert.match(source, /setOutputDirectory\(config\.html_parse_output_directory \|\| ""\)/);
  assert.match(modeHandler, /saveSetting\("html_parse_mode", preset\.mode\)/);
  assert.match(source, /saveSetting\("html_parser_method", val\)/);
  assert.match(source, /WorkflowPathSettings id="parse-separate-output-directory" fields=\{parsePathFields\}/);
});

test("html parse page loads modes and parsing methods from their own sources", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.match(source, /listDisclosureConditionPresets\(dataRoot\)/);
  assert.match(source, /apiGet<\{ methods: ParserMethodConfig\[\] \}>\("\/api\/disclosures\/html\/parse\/methods"\)/);
  assert.match(source, /<span>모드<\/span>[\s\S]*?presets\.map/);
  assert.match(source, /<span>파싱 방법<\/span>[\s\S]*?parserMethods\.map/);
  assert.doesNotMatch(source, /const DISCLOSURE_PARSE_MODES/);
  assert.doesNotMatch(source, /const PARSE_MODE_CONFIGS/);
});

test("html parse conversion settings describe the selected parser method", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.match(source, /<CardTitle className="dark:text-white">변환 설정<\/CardTitle>/);
  assert.match(source, /const selectedParserMethod = parserMethods\.find/);
  assert.match(source, /selectedParserMethod\.description/);
  assert.match(source, /selectedParserMethod\.status/);
});

test("html parse page renders report preview box for selected mode", async () => {
  const source = await readFile(pagePath, "utf8");
  const previewCardContent = source.match(/<CardTitle className="dark:text-white">리포트 미리보기<\/CardTitle>[\s\S]*?<CardTitle className="dark:text-white">작업 실행<\/CardTitle>/)?.[0] ?? "";

  assert.match(source, /const selectedParserMethod = parserMethods\.find/);
  assert.match(source, /parser_method: parserMethod/);
  assert.match(source, /const \[previewLoading, setPreviewLoading\] = useState\(false\)/);
  assert.match(source, /const \[previewData, setPreviewData\] = useState<any>\(null\)/);
  assert.match(source, /\/api\/disclosures\/html\/parse\/preview/);
  assert.match(source, /limit: 3/);
  assert.match(source, /<CardHeader className="flex flex-col gap-3 pb-4 md:flex-row md:items-start md:justify-between md:space-y-0">/);
  assert.match(source, /<div className="min-w-0 space-y-1">[\s\S]*?<CardTitle className="dark:text-white">리포트 미리보기<\/CardTitle>/);
  assert.doesNotMatch(previewCardContent, /<p className="mt-1 text-sm/);
  assert.doesNotMatch(previewCardContent, /리포트 최대 3건의 파싱 결과를 표로 확인/);
  assert.match(previewCardContent, /미리보기 불러오기/);
  assert.match(previewCardContent, /파싱 결과/);
  assert.match(source, /const renderParsedValue = \(value: any\): any =>/);
  assert.match(source, /text-\[11px\] leading-5/);
  assert.match(source, /px-3 py-2 align-top text-left/);
  assert.match(source, /const parsedValueIndexClassName =/);
  assert.match(source, /<table className=\{parsedValueTableClassName\}>/);
  assert.match(previewCardContent, /rounded-md border border-slate-200 bg-white px-4 py-3/);
  assert.doesNotMatch(previewCardContent, /rounded-md border border-slate-200 bg-white p-3/);
  assert.match(previewCardContent, /renderParsedValue\(record\.parsed_result\)/);
  assert.doesNotMatch(previewCardContent, /리포트 내용/);
  assert.doesNotMatch(previewCardContent, /JSON\.stringify\(record\.parsed_result, null, 2\)/);
  assert.doesNotMatch(source, /const PARSE_REVIEW_MENU = \[/);
  assert.doesNotMatch(source, /모드별 확인/);
});

test("html parse page does not auto generate output paths", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.doesNotMatch(source, /buildParseOutputPath/);
  assert.doesNotMatch(source, /parsed-\$\{mode\}\.json/);
  assert.doesNotMatch(source, /if \(config\.html_parse_result_path\)/);
  assert.doesNotMatch(source, /setOutputPath/);
  assert.doesNotMatch(source, /`\$\{input\}\/parsed-\$\{mode\}\.json`/);
  assert.doesNotMatch(source, /`\$\{initialInput\}\/parsed-/);
  assert.doesNotMatch(source, /output_root \? `\$\{config\.output_root\}\/viewer_html`/);
  assert.match(source, /setOutputDirectory\(config\.html_parse_output_directory \|\| ""\)/);
  assert.match(source, /setInputDirectory\(config\.html_section_split_output_directory \|\| ""\)/);
  assert.match(source, /output_directory: useSeparateOutputDirectory \? outputDirectory : ""/);
  assert.doesNotMatch(source, /output_path: output/);
});

test("html parse page removes resume and excel export controls", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.doesNotMatch(source, /resumeParse/);
  assert.doesNotMatch(source, /이어하기/);
  assert.doesNotMatch(source, /exportLatestOnly/);
  assert.doesNotMatch(source, /최신버전만 보기/);
  assert.doesNotMatch(source, /Excel로 내보내기/);
  assert.doesNotMatch(source, /FileSpreadsheet/);
  assert.doesNotMatch(source, /handleExport/);
  assert.doesNotMatch(source, /latest_only/);
  assert.doesNotMatch(source, /\/api\/disclosures\/html\/parse\/export\.xlsx/);
  assert.match(source, /className="grid gap-3 md:grid-cols-2"/);
});

test("html parse page sends parallel worker count", async () => {
  const source = await readFile(pagePath, "utf8");
  const inspectionPayload = source.match(/const buildParseInspectionPayload = \(\) => \(\{[\s\S]*?\}\);/)?.[0] ?? "";
  const settingsBlock = source.match(/const parseOptionFields: HtmlWorkflowField\[\][\s\S]*?\n  \];/)?.[0] ?? "";

  assert.match(source, /const \[parallelWorkers, setParallelWorkers\] = useState\(""\)/);
  assert.match(source, /const \[progressInterval, setProgressInterval\] = useState\("1000"\)/);
  assert.match(inspectionPayload, /parallel_workers: parallelWorkers \? Number\(parallelWorkers\) : null/);
  assert.match(settingsBlock, /id: "parallelWorkers"[\s\S]*?label: SETTINGS_LABELS\.workerCount/);
  assert.doesNotMatch(settingsBlock, /help:/);
  assert.match(source, /parallel_worker_count: defaultParallelWorkers/);
});

test("html parse page renders parser-method filters in a separate options card", async () => {
  const source = await readFile(pagePath, "utf8");
  const candidateCardSource = await readFile(candidateCardPath, "utf8");
  const settingsCardContent = source.match(/<CardTitle className="dark:text-white">변환 설정<\/CardTitle>[\s\S]*?<\/CardContent>\s*<\/Card>/)?.[0] ?? "";
  const optionsCardContent = source.match(/<CardTitle className="dark:text-white">실행 옵션<\/CardTitle>[\s\S]*?<CardTitle className="dark:text-white">리포트 미리보기<\/CardTitle>/)?.[0] ?? "";
  const inspectionPayload = source.match(/const buildParseInspectionPayload = \(\) => \(\{[\s\S]*?\}\);/)?.[0] ?? "";
  const methodHandler = source.match(/const handleParserMethodChange = \(val: string\) => \{[\s\S]*?\};/)?.[0] ?? "";

  assert.match(source, /type ParserMethodConfig =/);
  assert.match(source, /\/api\/disclosures\/html\/parse\/methods/);
  assert.doesNotMatch(source, /key: "bond_issuance"/);
  assert.doesNotMatch(source, /key: "rights_issuance"/);
  assert.match(source, /const \[selectedExecutionOptionValues, setSelectedExecutionOptionValues\] = useState<string\[\]>\(\[\]\)/);
  assert.match(source, /const \[executionOptionInputDirectory, setExecutionOptionInputDirectory\] = useState\(""\)/);
  assert.match(source, /const filterCandidatesRequestIdRef = useRef\(0\)/);
  assert.match(source, /type FilterCandidateExample =/);
  assert.match(source, /type ExecutionOptionExampleNotice =/);
  assert.match(source, /const \[executionOptionExampleNotice, setExecutionOptionExampleNotice\] = useState<ExecutionOptionExampleNotice \| null>\(null\)/);
  assert.match(source, /const \[notificationResetKey, setNotificationResetKey\] = useState\(0\)/);
  assert.match(source, /const executionOptionExampleUrl = \(example: FilterCandidateExample, inputDirectory: string\) =>/);
  assert.match(source, /acpt_no: acptNo/);
  assert.doesNotMatch(source, /String\(item\.acpt_no \|\| ""\)\.trim\(\)/);
  assert.doesNotMatch(source, /String\(example\.acpt_no \|\| ""\)\.trim\(\)/);
  assert.match(source, /const selectedParserMethod = parserMethods\.find/);
  assert.match(source, /const executionOptionConfig = selectedParserMethod\?\.filters\[0\] \|\| null/);
  assert.doesNotMatch(settingsCardContent, /실행 옵션/);
  assert.match(source, /DisclosureFilterCandidateCard/);
  assert.match(source, /title="실행 옵션"/);
  assert.match(source, /fieldLabel=\{executionOptionConfig\.field\}/);
  assert.match(source, /candidates=\{executionOptionCandidates\}/);
  assert.match(source, /selectedValues=\{selectedExecutionOptionValues\}/);
  assert.match(source, /loading=\{filterCandidatesLoading\}/);
  assert.match(source, /onLoadCandidates=\{handleLoadExecutionOptionCandidates\}/);
  assert.match(source, /onToggleValue=\{handleToggleExecutionOptionValue\}/);
  assert.match(source, /onShowExamples=\{handleShowExecutionOptionExamples\}/);
  assert.match(candidateCardSource, /export function DisclosureFilterCandidateCard/);
  assert.match(candidateCardSource, /eyebrow = "Execution Options"/);
  assert.match(candidateCardSource, /<CardTitle className="dark:text-white">\{title\}<\/CardTitle>/);
  assert.match(candidateCardSource, /<Label className="shrink-0 text-sm font-semibold text-slate-900 dark:text-slate-100">\{fieldLabel\}<\/Label>/);
  assert.doesNotMatch(optionsCardContent, />추가</);
  assert.doesNotMatch(optionsCardContent, /placeholder="예: 공모"/);
  assert.doesNotMatch(optionsCardContent, /불러오기를 누르면 입력 경로 전체에서 발견된 후보를 선택할 수 있습니다/);
  assert.doesNotMatch(optionsCardContent, /선택한 사채발행방법이 없으면 전체를 변환합니다/);
  assert.doesNotMatch(optionsCardContent, /후보가 표시됩니다/);
  assert.doesNotMatch(optionsCardContent, /selectedIssueMethods\.map/);
  assert.doesNotMatch(candidateCardSource, /max-h-72/);
  assert.match(candidateCardSource, /<CardHeader className="flex flex-col gap-3 pb-4 md:flex-row md:items-start md:justify-between md:space-y-0">/);
  assert.match(candidateCardSource, /rounded-lg border border-slate-200 bg-slate-50\/80/);
  assert.match(candidateCardSource, /lg:grid-cols-\[minmax\(0,1fr\)_auto\]/);
  assert.doesNotMatch(candidateCardSource, /선택한 후보/);
  assert.doesNotMatch(candidateCardSource, /후보를 선택하세요/);
  assert.match(candidateCardSource, /max-h-44/);
  assert.match(candidateCardSource, /border-slate-300 bg-slate-100\/80/);
  assert.doesNotMatch(candidateCardSource, /(?:text|bg|border)-teal-/);
  assert.match(candidateCardSource, /불러오기/);
  assert.match(candidateCardSource, /예시/);
  assert.match(candidateCardSource, /onToggleValue\(candidate\.value, !!value\)/);
  assert.match(candidateCardSource, /onShowExamples\(candidate\)/);
  assert.match(source, /\/api\/disclosures\/html\/parse\/filter-candidates/);
  assert.match(source, /DisclosureConditionFilterCard/);
  assert.match(source, /filter_blocks: normalizeDisclosureConditionBlocks\(conditions\)/);
  assert.match(methodHandler, /setSelectedExecutionOptionValues\(\[\]\)/);
  assert.match(methodHandler, /setExecutionOptionCandidates\(\[\]\)/);
  assert.match(methodHandler, /setExecutionOptionExampleNotice\(null\)/);
  assert.match(methodHandler, /setFilterCandidatesLoading\(false\)/);
  assert.match(source, /filterCandidatesRequestIdRef\.current \+= 1/);
  assert.match(source, /if \(filterCandidatesRequestIdRef\.current !== requestId\) return/);
  assert.match(source, /notificationActive=\{isErrorStatus \|\| !!executionOptionExampleNotice \|\| warningReports\.length > 0\}/);
  assert.match(source, /notificationTone=\{isErrorStatus \? "error" : warningReports\.length > 0 \|\| executionOptionExampleNotice \? "warning" : "neutral"\}/);
  assert.match(source, /notificationResetKey=\{notificationResetKey\}/);
  assert.match(source, /setNotificationResetKey\(\(current\) => current \+ 1\)/);
  assert.match(source, /executionOptionExampleNotice \? \(/);
  assert.match(source, /executionOptionExampleNotice\.examples\.map/);
  assert.match(source, /window\.open\(executionOptionExampleUrl\(example, executionOptionInputDirectory\), "_blank", "noopener,noreferrer"\)/);
  assert.match(source, />\s*열기\s*</);
  assert.match(inspectionPayload, /record_filters: activeRecordFilters/);
  assert.match(source, /const activeRecordFilters = executionOptionConfig[\s\S]*?field: executionOptionConfig\.field/);
  assert.match(source, /const activeRecordFilters = executionOptionConfig[\s\S]*?operator: "in"/);
});
