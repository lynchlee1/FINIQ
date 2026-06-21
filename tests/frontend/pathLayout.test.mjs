import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlSectionSplitPath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
const tablePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx";

test("html section split path fields stack vertically", async () => {
  const source = await readFile(htmlSectionSplitPath, "utf8");
  const pathFieldsBlock = source.match(/const splitPathFields:[\s\S]*?const splitOptionFields:/)?.[0] ?? "";

  assert.match(pathFieldsBlock, /id: "inputDirectory"[\s\S]*?span: 4/);
  assert.match(pathFieldsBlock, /id: "outputDirectory"[\s\S]*?span: 4/);
});

test("disclosure table conversion path fields stack vertically", async () => {
  const source = await readFile(tablePagePath, "utf8");

  assert.match(source, /<CardTitle className="dark:text-white">데이터 경로<\/CardTitle>/);
  assert.doesNotMatch(source, /<div className="grid gap-4 md:grid-cols-2">/);
});
