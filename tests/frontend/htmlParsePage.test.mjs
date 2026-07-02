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
  assert.match(source, /notificationActive=\{isErrorStatus\}/);
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
  const modeCardContent = source.match(/<CardTitle className="dark:text-white">모드별 기능<\/CardTitle>[\s\S]*?{PARSE_MODES\.map/)?.[0] ?? "";

  assert.match(modeCardContent, /className="grid gap-3"/);
  assert.doesNotMatch(modeCardContent, /md:grid-cols-2/);
});

test("html parse mode cards use readable list row spacing", async () => {
  const source = await readFile(pagePath, "utf8");
  const modeCardContent = source.match(/<CardTitle className="dark:text-white">모드별 기능<\/CardTitle>[\s\S]*?{PARSE_MODES\.map[\s\S]*?<\/CardContent>/)?.[0] ?? "";

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

  assert.match(source, /const selectedParseMode = PARSE_MODES\.find/);
  assert.match(source, /const \[previewLoading, setPreviewLoading\] = useState\(false\)/);
  assert.match(source, /const \[previewData, setPreviewData\] = useState<any>\(null\)/);
  assert.match(source, /\/api\/disclosures\/html\/parse\/preview/);
  assert.match(source, /limit: 3/);
  assert.match(previewCardContent, /리포트 최대 3건의 파싱 결과를 표로 확인/);
  assert.match(previewCardContent, /미리보기 불러오기/);
  assert.match(previewCardContent, /파싱 결과/);
  assert.match(source, /const renderParsedValue = \(value: any\): any =>/);
  assert.match(source, /text-\[11px\] leading-5/);
  assert.match(source, /px-3 py-2 align-top text-left/);
  assert.match(source, /const parsedValueIndexClassName =/);
  assert.match(source, /<table className=\{parsedValueTableClassName\}>/);
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
