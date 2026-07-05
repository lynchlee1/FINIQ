import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const pagePath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/app/html-parse/page.tsx");

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

test("html parse notification panel lists warning reports and reasons", async () => {
  const source = await readFile(pagePath, "utf8");
  const notificationContent = source.match(/notificationContent=\{[\s\S]*?settingsTitle="시스템 설정"/)?.[0] ?? "";

  assert.match(source, /type ParseWarningItem =/);
  assert.match(source, /const buildWarningReports = \(warnings: ParseWarningItem\[\]\): WarningReport\[\] =>/);
  assert.match(source, /const warningSourceUrl = \(sourceFile: string, inputDirectory: string\) =>/);
  assert.match(source, /\/api\/disclosures\/html\/sections\/source\?/);
  assert.match(source, /return fileUrl\(sourceFile\)/);
  assert.match(source, /const WARNING_OPEN_PAGE_SIZE = 20/);
  assert.match(source, /onSuccess: \(result\) => \{[\s\S]*?setLatestParseResult\(result\)/);
  assert.match(source, /setLatestParseResult\(null\)/);
  assert.match(source, /const warningReports = buildWarningReports/);
  assert.match(source, /const warningSourceFiles = Array\.from\(new Set\(warningReports\.map/);
  assert.match(source, /const warningPageSourceFiles = warningSourceFiles\.slice\(warningPageStartIndex, warningPageStartIndex \+ WARNING_OPEN_PAGE_SIZE\)/);
  assert.match(source, /const handleOpenWarningFiles = \(\) => \{[\s\S]*?warningPageSourceFiles\.forEach[\s\S]*?window\.open\(warningSourceUrl\(sourceFile, inputDirectory\), "_blank", "noopener,noreferrer"\)/);
  assert.match(notificationContent, /경고 리포트/);
  assert.match(notificationContent, /현재 페이지 열기/);
  assert.match(notificationContent, /이전/);
  assert.match(notificationContent, /다음/);
  assert.match(notificationContent, /disabled=\{!warningSourceFiles\.length\}/);
  assert.match(notificationContent, /warningReports\.map/);
  assert.match(notificationContent, /report\.sourceName/);
  assert.match(notificationContent, /report\.sourceFile/);
  assert.match(notificationContent, /report\.warnings\.map/);
});

test("html parse page uses standard two-row data path card", async () => {
  const source = await readFile(pagePath, "utf8");
  const pathFieldsBlock = source.match(/const parseSettingFields:[\s\S]*?const parsePathFields =/)?.[0] ?? "";
  const dataPathCard = source.match(/<HtmlWorkflowCard[\s\S]*?title="데이터 경로"[\s\S]*?>/)?.[0] ?? "";

  assert.match(pathFieldsBlock, /id: "inputDirectory"[\s\S]*?span: 4/);
  assert.match(pathFieldsBlock, /id: "outputPath"[\s\S]*?span: 4/);
  assert.match(source, /title="데이터 경로"/);
  assert.doesNotMatch(source, /title="공시원문 변환 경로"/);
  assert.doesNotMatch(dataPathCard, /description=/);
});

test("html parse page persists generated data paths", async () => {
  const source = await readFile(pagePath, "utf8");
  const inputHandler = source.match(/const handleInputDirectoryChange =[\s\S]*?};/)?.[0] ?? "";
  const modeHandler = source.match(/const handleParseModeChange =[\s\S]*?};/)?.[0] ?? "";

  assert.match(inputHandler, /const nextOutputPath = buildParseOutputPath\(val, parseMode\)/);
  assert.match(inputHandler, /setOutputPath\(nextOutputPath\)/);
  assert.match(inputHandler, /saveSettings\(\{\s*html_content_output_directory: val,\s*html_parse_result_path: nextOutputPath,\s*\}\)/);
  assert.doesNotMatch(inputHandler, /html_output_directory/);
  assert.match(modeHandler, /const nextOutputPath = buildParseOutputPath\(inputDirectory, val\)/);
  assert.match(modeHandler, /setOutputPath\(nextOutputPath\)/);
  assert.match(modeHandler, /saveSettings\(\{\s*html_parse_mode: val,\s*html_parse_result_path: nextOutputPath,\s*\}\)/);
});

test("html parse mode cards render as full-width rows", async () => {
  const source = await readFile(pagePath, "utf8");
  const modeCardContent = source.match(/<CardTitle className="dark:text-white">모드별 기능<\/CardTitle>[\s\S]*?{DISCLOSURE_PARSE_MODES\.map/)?.[0] ?? "";

  assert.match(modeCardContent, /className="grid gap-3"/);
  assert.doesNotMatch(modeCardContent, /md:grid-cols-2/);
});

test("html parse mode cards use readable list row spacing", async () => {
  const source = await readFile(pagePath, "utf8");
  const modeCardContent = source.match(/<CardTitle className="dark:text-white">모드별 기능<\/CardTitle>[\s\S]*?{DISCLOSURE_PARSE_MODES\.map[\s\S]*?<\/CardContent>/)?.[0] ?? "";

  assert.match(source, /<CardHeader className="gap-3 pb-4">[\s\S]*?<CardTitle className="dark:text-white">모드별 기능<\/CardTitle>/);
  assert.match(source, /<CardContent className="space-y-4">[\s\S]*?<div className="grid gap-3">/);
  assert.match(modeCardContent, /rounded-md border px-4 py-3/);
  assert.match(modeCardContent, /transition-shadow/);
  assert.doesNotMatch(modeCardContent, /transition-all/);
  assert.match(modeCardContent, /shadow-sm/);
  assert.match(modeCardContent, /<div className="flex items-center gap-2">/);
  assert.match(modeCardContent, /<p className="mt-2 text-xs leading-6 opacity-85">/);
  assert.doesNotMatch(modeCardContent, /p-4 rounded-xl/);
  assert.doesNotMatch(modeCardContent, /leading-relaxed/);
});

test("html parse page renders report preview box for selected mode", async () => {
  const source = await readFile(pagePath, "utf8");
  const previewCardContent = source.match(/<CardTitle className="dark:text-white">리포트 미리보기<\/CardTitle>[\s\S]*?<CardTitle className="dark:text-white">작업 실행<\/CardTitle>/)?.[0] ?? "";

  assert.match(source, /const selectedParseMode = PARSE_MODE_CONFIGS\[parseMode\] \|\| DISCLOSURE_PARSE_MODES\[0\]/);
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

test("html parse page normalizes auto generated output paths", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.match(source, /const buildParseOutputPath = \(inputDirectory: string, mode: string\)/);
  assert.match(source, /trimmedInputDirectory\.replace\(\/\\\/\+\$\/, ""\)/);
  assert.match(source, /\["kind_html_contents_grouped_sections", "kind_html_contents_sections"\]/);
  assert.match(source, /normalizedInputDirectory\.endsWith\(`\/\$\{directoryName\}`\)/);
  assert.match(source, /normalizedInputDirectory\.slice\(0, -htmlContentDirectory\.length\)/);
  assert.doesNotMatch(source, /if \(config\.html_parse_result_path\)/);
  assert.doesNotMatch(source, /setOutputPath\(config\.html_parse_result_path\)/);
  assert.doesNotMatch(source, /`\$\{input\}\/parsed-\$\{mode\}\.json`/);
  assert.doesNotMatch(source, /`\$\{initialInput\}\/parsed-/);
});

test("html parse page defaults resume off and removes excel export controls", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.match(source, /const \[resumeParse, setResumeParse\] = useState\(false\)/);
  assert.doesNotMatch(source, /useState\(true\);\n\s*const \[progressInterval/);
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
  const runHandler = source.match(/const handleRun = async \(\) => \{[\s\S]*?startJob\("\/api\/disclosures\/html\/parse\/start", payload\);[\s\S]*?\};/)?.[0] ?? "";
  const settingsBlock = source.match(/const parseSettingFields:[\s\S]*?const parsePathFields =/)?.[0] ?? "";

  assert.match(source, /const \[parallelWorkers, setParallelWorkers\] = useState\(""\)/);
  assert.match(source, /const \[progressInterval, setProgressInterval\] = useState\("1000"\)/);
  assert.match(runHandler, /parallel_workers: parallelWorkers \? Number\(parallelWorkers\) : null/);
  assert.match(settingsBlock, /id: "parallelWorkers"[\s\S]*?label: "병렬 워커 수"/);
  assert.match(settingsBlock, /help: "앱 최초 접속 시 확인한 CPU 기준 기본값을 사용합니다\."/);
  assert.match(source, /parallel_worker_count: defaultParallelWorkers/);
});

test("html parse page renders parse-mode specific filters in separate options card", async () => {
  const source = await readFile(pagePath, "utf8");
  const modeCardContent = source.match(/<CardTitle className="dark:text-white">모드별 기능<\/CardTitle>[\s\S]*?<\/CardContent>\s*<\/Card>/)?.[0] ?? "";
  const optionsCardContent = source.match(/<CardTitle className="dark:text-white">실행 옵션<\/CardTitle>[\s\S]*?<CardTitle className="dark:text-white">리포트 미리보기<\/CardTitle>/)?.[0] ?? "";
  const runHandler = source.match(/const handleRun = async \(\) => \{[\s\S]*?startJob\("\/api\/disclosures\/html\/parse\/start", payload\);[\s\S]*?\};/)?.[0] ?? "";
  const modeHandler = source.match(/const handleParseModeChange = \(val: string\) => \{[\s\S]*?\};/)?.[0] ?? "";

  assert.match(source, /type ParseModeConfig =/);
  assert.match(source, /const DISCLOSURE_PARSE_MODES: ParseModeConfig\[\] = \[/);
  assert.match(source, /key: "bond_issuance"[\s\S]*?executionOptions: \[\{ field: "사채발행방법", statusLabel: "사채발행방법" \}\]/);
  assert.match(source, /key: "rights_issuance"[\s\S]*?executionOptions: \[\{ field: "증자방식", statusLabel: "증자방식" \}\]/);
  assert.match(source, /const PARSE_MODE_CONFIGS = Object\.fromEntries\(DISCLOSURE_PARSE_MODES\.map/);
  assert.match(source, /const \[selectedExecutionOptionValues, setSelectedExecutionOptionValues\] = useState<string\[\]>\(\[\]\)/);
  assert.match(source, /type FilterCandidateExample =/);
  assert.match(source, /type ExecutionOptionExampleNotice =/);
  assert.match(source, /const \[executionOptionExampleNotice, setExecutionOptionExampleNotice\] = useState<ExecutionOptionExampleNotice \| null>\(null\)/);
  assert.match(source, /const \[notificationResetKey, setNotificationResetKey\] = useState\(0\)/);
  assert.match(source, /const executionOptionExampleUrl = \(example: FilterCandidateExample, inputDirectory: string\) =>/);
  assert.match(source, /source_name: sourceName/);
  assert.match(source, /const selectedParseMode = PARSE_MODE_CONFIGS\[parseMode\] \|\| DISCLOSURE_PARSE_MODES\[0\]/);
  assert.match(source, /const executionOptionConfig = selectedParseMode\.executionOptions\[0\] \|\| null/);
  assert.doesNotMatch(modeCardContent, /실행 옵션/);
  assert.match(optionsCardContent, /executionOptionConfig\.field/);
  assert.doesNotMatch(optionsCardContent, />추가</);
  assert.doesNotMatch(optionsCardContent, /placeholder="예: 공모"/);
  assert.doesNotMatch(optionsCardContent, /불러오기를 누르면 입력 경로 전체에서 발견된 후보를 선택할 수 있습니다/);
  assert.doesNotMatch(optionsCardContent, /선택한 사채발행방법이 없으면 전체를 변환합니다/);
  assert.doesNotMatch(optionsCardContent, /후보가 표시됩니다/);
  assert.doesNotMatch(optionsCardContent, /selectedIssueMethods\.map/);
  assert.doesNotMatch(optionsCardContent, /max-h-72/);
  assert.match(optionsCardContent, /className="flex justify-end"/);
  assert.match(optionsCardContent, /className="grid gap-2 lg:grid-cols-2"/);
  assert.match(optionsCardContent, /lg:col-span-2/);
  assert.match(optionsCardContent, /max-h-44/);
  assert.match(optionsCardContent, /불러오기/);
  assert.match(optionsCardContent, /예시/);
  assert.match(optionsCardContent, /handleToggleExecutionOptionValue/);
  assert.match(optionsCardContent, /handleShowExecutionOptionExamples\(candidate\)/);
  assert.match(source, /\/api\/disclosures\/html\/parse\/filter-candidates/);
  assert.match(modeHandler, /setSelectedExecutionOptionValues\(\[\]\)/);
  assert.match(modeHandler, /setExecutionOptionCandidates\(\[\]\)/);
  assert.match(modeHandler, /setExecutionOptionExampleNotice\(null\)/);
  assert.match(source, /notificationActive=\{isErrorStatus \|\| !!executionOptionExampleNotice \|\| warningReports\.length > 0\}/);
  assert.match(source, /notificationResetKey=\{notificationResetKey\}/);
  assert.match(source, /setNotificationResetKey\(\(current\) => current \+ 1\)/);
  assert.match(source, /executionOptionExampleNotice \? \(/);
  assert.match(source, /executionOptionExampleNotice\.examples\.map/);
  assert.match(source, /window\.open\(executionOptionExampleUrl\(example, inputDirectory\), "_blank", "noopener,noreferrer"\)/);
  assert.match(source, />\s*열기\s*</);
  assert.match(runHandler, /record_filters: activeRecordFilters/);
  assert.match(runHandler, /field: executionOptionConfig\.field/);
  assert.match(runHandler, /operator: "in"/);
});
