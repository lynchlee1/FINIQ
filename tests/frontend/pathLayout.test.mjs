import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlSectionSplitPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
const tablePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx";

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
