import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "../../frontend/node_modules/typescript/lib/typescript.js";

const disclosureConditionCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureConditionFilterCard.tsx";

async function loadHelper() {
  const source = await readFile(disclosureConditionCardPath, "utf8");
  const helper = source.match(/export function nextValueAfterModifierBackspace\([\s\S]*?\n\}/)?.[0];
  assert.ok(helper, "nextValueAfterModifierBackspace helper must exist");
  const compiled = ts.transpileModule(helper, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const tempPath = path.join(tmpdir(), `finiq-filter-backspace-${Date.now()}-${Math.random()}.mjs`);
  await writeFile(tempPath, compiled.outputText);
  return import(pathToFileURL(tempPath).href);
}

async function loadNormalizationHelper() {
  const source = await readFile(disclosureConditionCardPath, "utf8");
  const declarations = [
    source.match(/export function makeEmptyDisclosureCondition\([\s\S]*?\n\}/)?.[0],
    source.match(/function isEmptyDisclosureConditionBlocks\([\s\S]*?\n\}/)?.[0],
    source.match(/export function normalizeDisclosureConditionBlocks\([\s\S]*?\n\}/)?.[0],
  ];
  declarations.forEach((declaration) => assert.ok(declaration));
  const compiled = ts.transpileModule(
    `const DISCLOSURE_FILTER_FIELD_OPTIONS = [["title", "제목"]];\n`
      + `function isOperatorAllowedForField() { return true; }\n`
      + declarations.join("\n"),
    {
      compilerOptions: {
        module: ts.ModuleKind.ES2022,
        target: ts.ScriptTarget.ES2022,
      },
    },
  );
  const tempPath = path.join(tmpdir(), `finiq-filter-normalize-${Date.now()}-${Math.random()}.mjs`);
  await writeFile(tempPath, compiled.outputText);
  return import(pathToFileURL(tempPath).href);
}

test("condition search filter Command+Backspace clears the controlled value", async () => {
  const source = await readFile(disclosureConditionCardPath, "utf8");
  const { nextValueAfterModifierBackspace } = await loadHelper();

  assert.match(source, /\(event\.metaKey \|\| event\.ctrlKey\) && event\.key === "Backspace"/);
  assert.match(source, /event\.preventDefault\(\);\s*const input = event\.currentTarget;\s*onValueChange\(nextValueAfterModifierBackspace/);
  assert.equal(nextValueAfterModifierBackspace("bond_issuance", 14, 14, true), "");
  assert.equal(nextValueAfterModifierBackspace("bond_issuance", 0, 14, true), "");
  assert.equal(nextValueAfterModifierBackspace("bond_issuance", 5, 5, true), "issuance");
  assert.equal(nextValueAfterModifierBackspace("bond_issuance", 5, 5, false), "issuance");
  assert.equal(nextValueAfterModifierBackspace("bond issuance", 13, 13, false), "bond ");
});

test("between conditions require exactly two values before save or execution", async () => {
  const source = await readFile(disclosureConditionCardPath, "utf8");

  assert.match(source, /if \(row\.operator === "between"\)/);
  assert.match(source, /if \(values\.length !== 2\)/);
  assert.match(source, /between operator requires exactly two values/);
});

test("the untouched empty condition serializes as no filter blocks", async () => {
  const {
    makeEmptyDisclosureCondition,
    normalizeDisclosureConditionBlocks,
  } = await loadNormalizationHelper();

  assert.deepEqual(
    normalizeDisclosureConditionBlocks([makeEmptyDisclosureCondition()]),
    [],
  );
  assert.throws(
    () => normalizeDisclosureConditionBlocks([
      { ...makeEmptyDisclosureCondition(), not: true },
    ]),
    /value is required/,
  );
});
