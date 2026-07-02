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
  assert.doesNotMatch(source, /Label className="dark:text-slate-300">파싱 경고/);
  assert.match(source, /notificationActive=\{isErrorStatus\}/);
});

test("html parse page normalizes auto generated output paths", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.match(source, /const buildParseOutputPath = \(inputDirectory: string, mode: string\)/);
  assert.match(source, /trimmedInputDirectory\.replace\(\/\\\/\+\$\/, ""\)/);
  assert.doesNotMatch(source, /`\$\{input\}\/parsed-\$\{mode\}\.json`/);
  assert.doesNotMatch(source, /`\$\{initialInput\}\/parsed-/);
});
