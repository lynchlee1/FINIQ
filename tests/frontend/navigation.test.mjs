import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "../../frontend/node_modules/typescript/lib/typescript.js";

async function loadNavigation() {
  const sourcePath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/config/navigation.ts");
  const source = await readFile(sourcePath, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const tempPath = path.join(tmpdir(), `finiq-navigation-${Date.now()}-${Math.random()}.mjs`);
  await writeFile(tempPath, compiled.outputText);
  return import(pathToFileURL(tempPath).href);
}

test("top navigation separates disclosure, price data, and utility scopes", async () => {
  const { NAV_ITEMS, getActiveNavItem } = await loadNavigation();

  assert.deepEqual(
    NAV_ITEMS.map((item) => item.label),
    ["Ontology", "공시데이터", "주가데이터", "유틸리티"],
  );
  assert.equal(getActiveNavItem("/download")?.label, "공시데이터");
  assert.equal(getActiveNavItem("/html-parse")?.label, "공시데이터");
  assert.equal(getActiveNavItem("/utility/assets-excel/convert")?.label, "주가데이터");
  assert.equal(getActiveNavItem("/utility")?.label, "유틸리티");
});

test("sidebar definitions match the narrowed top-level workflows", async () => {
  const { getSidebarDefinition } = await loadNavigation();

  assert.deepEqual(
    getSidebarDefinition("disclosure-build").groups.map((group) => group.label),
    ["공시 제목 분석", "공시 내용 분석"],
  );

  const priceDataSidebar = getSidebarDefinition("price-data");
  assert.deepEqual(priceDataSidebar.groups.map((group) => group.label), ["Quantiwise"]);
  assert.deepEqual(
    priceDataSidebar.groups[0].steps.map((step) => step.label),
    ["Excel 미리보기", "Parquet 변환하기", "Parquet 미리보기", "Parquet 병합하기"],
  );

  const utilitySidebar = getSidebarDefinition("utility");
  assert.deepEqual(utilitySidebar.groups.map((group) => group.label), ["유틸리티"]);
  assert.deepEqual(utilitySidebar.groups[0].steps.map((step) => step.href), ["/utility"]);
});

test("ontology sidebar separates graph and disclosure analysis pages", async () => {
  const { getSidebarDefinition, getPageTitle } = await loadNavigation();
  const ontologySidebar = getSidebarDefinition("ontology");

  assert.deepEqual(
    ontologySidebar.groups[0].steps.map((step) => step.href),
    ["/graph", "/graph/analysis"],
  );
  assert.equal(getPageTitle("/graph"), "Graph View");
  assert.equal(getPageTitle("/graph/analysis"), "공시 분석");
});

test("price data pages use short page titles without repeating the top-level menu", async () => {
  const { getPageTitle } = await loadNavigation();

  assert.equal(getPageTitle("/utility/assets-excel"), "Excel 미리보기");
  assert.equal(getPageTitle("/utility/assets-excel/merge"), "Parquet 병합하기");
});
