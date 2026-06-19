import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "../../frontend/node_modules/typescript/lib/typescript.js";

async function loadDragSelection() {
  const helperPath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/features/assets-excel/dragSelection.ts");
  const source = await readFile(helperPath, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const tempPath = path.join(tmpdir(), `finiq-drag-selection-${Date.now()}-${Math.random()}.mjs`);
  await writeFile(tempPath, compiled.outputText);
  return import(pathToFileURL(tempPath).href);
}

test("dragSelectionTargetChecked flips the starting row state", async () => {
  const { dragSelectionTargetChecked } = await loadDragSelection();

  assert.equal(dragSelectionTargetChecked(false), true);
  assert.equal(dragSelectionTargetChecked(true), false);
});

test("applyFileSelection adds and removes files without duplicates", async () => {
  const { applyFileSelection } = await loadDragSelection();

  assert.deepEqual(applyFileSelection(["a.xlsx"], "b.xlsx", true), ["a.xlsx", "b.xlsx"]);
  assert.deepEqual(applyFileSelection(["a.xlsx"], "a.xlsx", true), ["a.xlsx"]);
  assert.deepEqual(applyFileSelection(["a.xlsx", "b.xlsx"], "a.xlsx", false), ["b.xlsx"]);
});

test("applyFileSelection respects add-only guards while still allowing removal", async () => {
  const { applyFileSelection } = await loadDragSelection();

  assert.deepEqual(applyFileSelection(["a.parquet"], "b.parquet", true, () => false), ["a.parquet"]);
  assert.deepEqual(applyFileSelection(["a.parquet"], "a.parquet", false, () => false), []);
});

test("applyFileSelection returns the same array when selection does not change", async () => {
  const { applyFileSelection } = await loadDragSelection();
  const selected = ["a.xlsx"];

  assert.equal(applyFileSelection(selected, "a.xlsx", true), selected);
  assert.equal(applyFileSelection(selected, "b.xlsx", true, () => false), selected);
  assert.equal(applyFileSelection(selected, "b.xlsx", false), selected);
});

test("selectionRowClassName adds subtle selected-row color", async () => {
  const { selectionRowClassName } = await loadDragSelection();

  assert.equal(selectionRowClassName(false), "dark:text-slate-300");
  assert.match(selectionRowClassName(true), /bg-sky-50\/70/);
  assert.match(selectionRowClassName(true), /dark:bg-sky-950\/30/);
});

test("formatMergeSelectionSummary keeps incomplete account warning inline", async () => {
  const { formatMergeSelectionSummary } = await loadDragSelection();

  assert.equal(
    formatMergeSelectionSummary("9", "4", ["adjVolume"]),
    "선택한 파일: 9개 / 묶음: 4개 (1개만 선택된 계정: adjVolume)",
  );
  assert.equal(
    formatMergeSelectionSummary("8", "4", []),
    "선택한 파일: 8개 / 묶음: 4개",
  );
});

test("selectFirstTwoFilesPerAccount selects up to two files per account", async () => {
  const { selectFirstTwoFilesPerAccount } = await loadDragSelection();

  assert.deepEqual(
    selectFirstTwoFilesPerAccount(
      ["volume_1.parquet", "volume_2.parquet", "volume_3.parquet", "price_1.parquet", "price_2.parquet"],
      (fileName) => fileName.split("_")[0],
    ),
    ["volume_1.parquet", "volume_2.parquet", "price_1.parquet", "price_2.parquet"],
  );
});

test("asset Excel selection headers prevent Korean label wrapping", async () => {
  const source = await readFile(
    "frontend/finiq_GUI/apps/market-desk/src/features/assets-excel/AssetExcelUtilityView.tsx",
    "utf8",
  );

  assert.match(source, /<th className="min-w-16 whitespace-nowrap px-3 py-2 font-medium">선택<\/th>/);
});
