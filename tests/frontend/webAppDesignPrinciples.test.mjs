import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const packageJsonPath = "frontend/finiq_GUI/packages/web-app/package.json";
const designPrinciplesPath = "frontend/finiq_GUI/packages/web-app/DESIGN_PRINCIPLES.md";
const sourceRoot = "frontend/finiq_GUI/packages/web-app/src";

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(entries.map(async (entry) => {
    const resolved = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(resolved);
    if (/\.(ts|tsx)$/.test(entry.name)) return [resolved];
    return [];
  }));
  return files.flat();
}

test("web-app package exposes focused entry points", async () => {
  const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));

  assert.deepEqual(Object.keys(packageJson.exports), [".", "./layout", "./workflow", "./status", "./path"]);
  assert.equal(packageJson.exports["./layout"].default, "./src/layout.ts");
  assert.equal(packageJson.exports["./workflow"].default, "./src/workflow.ts");
  assert.equal(packageJson.exports["./status"].default, "./src/status.ts");
  assert.equal(packageJson.exports["./path"].default, "./src/path.ts");
  assert.equal(packageJson.scripts.build, "tsc -p tsconfig.app.json");
});

test("web-app design principles document constrained financial UI rules", async () => {
  const source = await readFile(designPrinciplesPath, "utf8");

  assert.match(source, /reduce visual freedom, not expand it/);
  assert.match(source, /Notion-like restraint/);
  assert.match(source, /small, fixed set of text roles/);
  assert.match(source, /Avoid new arbitrary font sizes/);
  assert.match(source, /`@finiq\/ui` owns primitive controls/);
  assert.match(source, /`@finiq\/web-app` owns FINIQ workflow composition/);
  assert.match(source, /real financial data density/);
});

test("web-app source keeps design freedom constrained", async () => {
  const files = await sourceFiles(sourceRoot);
  const combined = (await Promise.all(files.map((file) => readFile(file, "utf8")))).join("\n");

  assert.doesNotMatch(combined, /text-\[[0-9.]+(?:px|rem|em)\]/);
  assert.doesNotMatch(combined, /bg-gradient|from-\[|to-\[|via-\[/);
  assert.doesNotMatch(combined, /rounded-(?:2xl|3xl)/);
  assert.doesNotMatch(combined, /shadow-(?:xl|2xl)/);
});
