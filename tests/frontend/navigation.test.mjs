import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "../../frontend/node_modules/typescript/lib/typescript.js";

const appFramePath = "frontend/finiq_GUI/apps/market-desk/src/components/layout/AppFrame.tsx";
const workflowPageShellPath = "frontend/finiq_GUI/apps/market-desk/src/components/layout/WorkflowPageShell.tsx";
const htmlWorkflowTemplatePath = "frontend/finiq_GUI/apps/market-desk/src/components/html-workflow/HtmlWorkflowTemplate.tsx";

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
  assert.equal(getActiveNavItem("/disclosure-automation")?.label, "공시데이터");
  assert.equal(getActiveNavItem("/html-parse")?.label, "공시데이터");
  assert.equal(getActiveNavItem("/utility/assets-excel/convert")?.label, "주가데이터");
  assert.equal(getActiveNavItem("/utility")?.label, "유틸리티");
});

test("sidebar definitions match the narrowed top-level workflows", async () => {
  const { getPageTitle, getSidebarDefinition } = await loadNavigation();

  const disclosureSidebar = getSidebarDefinition("disclosure-build");
  assert.deepEqual(
    disclosureSidebar.groups.map((group) => group.label),
    ["공시 자동화", "공시 제목 분석", "공시 내용 분석", "결과 검수"],
  );
  assert.deepEqual(
    disclosureSidebar.groups[0].steps.map((step) => step.href),
    ["/disclosure-automation"],
  );
  assert.ok(disclosureSidebar.groups.slice(0, 3).every((group) => group.numbered));
  assert.equal(disclosureSidebar.groups[3].numbered, undefined);
  assert.deepEqual(
    disclosureSidebar.groups
      .filter((group) => group.numbered)
      .flatMap((group) => group.steps.map((step) => [step.step, step.href])),
    [
      [0, "/disclosure-automation"],
      [1, "/download"],
      [2, "/table"],
      [3, "/filter"],
      [4, "/external-html-download"],
      [5, "/internal-html-download"],
      [6, "/html-section-split"],
      [7, "/html-parse"],
      [8, "/html-change-log"],
      [9, "/disclosure-graph"],
    ],
  );
  assert.equal(getPageTitle("/filter"), "공시내역 필터링");
  assert.deepEqual(
    disclosureSidebar.groups[3].steps.map((step) => [step.step, step.href, step.label]),
    [[undefined, "/html-bond-summary", "발행내역 한눈에"]],
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
  const { NAV_ITEMS, getSidebarDefinition, getPageTitle } = await loadNavigation();
  const ontologyNav = NAV_ITEMS.find((item) => item.label === "Ontology");
  const ontologySidebar = getSidebarDefinition("ontology");

  assert.equal(ontologyNav?.href, "/graph/chart");
  assert.deepEqual(
    ontologySidebar.groups[0].steps.map((step) => step.href),
    ["/graph/chart", "/graph", "/graph/analysis"],
  );
  assert.equal(getPageTitle("/graph/chart"), "Chart View");
  assert.equal(getPageTitle("/graph"), "Graph View");
  assert.equal(getPageTitle("/graph/analysis"), "공시 분석");
});

test("price data pages use short page titles without repeating the top-level menu", async () => {
  const { getPageTitle } = await loadNavigation();

  assert.equal(getPageTitle("/utility/assets-excel"), "Excel 미리보기");
  assert.equal(getPageTitle("/utility/assets-excel/merge"), "Parquet 병합하기");
});

test("disclosure navigation stays mounted while route content changes", async () => {
  const [appFrameSource, workflowShellSource, htmlTemplateSource] = await Promise.all([
    readFile(appFramePath, "utf8"),
    readFile(workflowPageShellPath, "utf8"),
    readFile(htmlWorkflowTemplatePath, "utf8"),
  ]);

  assert.match(appFrameSource, /activeItem\?\.workflowId === "disclosure-build"/);
  assert.match(appFrameSource, /<WorkflowSidebar title=\{sidebar\.title\} groups=\{sidebar\.groups\} \/>/);
  assert.match(appFrameSource, /data-testid="persistent-disclosure-layout"/);
  assert.match(workflowShellSource, /workflowId === "disclosure-build"[\s\S]*?return <>{children}<\/>/);
  assert.doesNotMatch(htmlTemplateSource, /<WorkflowSidebar/);
});
