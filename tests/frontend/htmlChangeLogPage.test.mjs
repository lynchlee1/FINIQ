import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-change-log/page.tsx";
const settingsPath = "frontend/finiq_GUI/apps/market-desk/src/components/html-change-log/ChangeLogSettings.tsx";
const matrixPath = "frontend/finiq_GUI/apps/market-desk/src/components/html-change-log/ChangeLogMatrix.tsx";
const matrixUtilsPath = "frontend/finiq_GUI/apps/market-desk/src/utils/matrixUtils.ts";
const sidebarPath = "frontend/finiq_GUI/packages/web-app/src/components/layout/WorkflowSidebar.tsx";

test("08 correction history page exposes its implemented threshold settings", async () => {
  const [pageSource, settingsSource] = await Promise.all([
    readFile(pagePath, "utf8"),
    readFile(settingsPath, "utf8"),
  ]);

  assert.match(pageSource, /import \{ ChangeLogSettings \} from "@\/components\/html-change-log\/ChangeLogSettings"/);
  assert.match(pageSource, /settingsContent=\{[\s\S]*?<ChangeLogSettings \/>/);
  assert.match(settingsSource, /변동 임계값/);
  assert.match(settingsSource, /DATE_FIELDS_CONFIG/);
  assert.match(settingsSource, /NUMERIC_FIELDS_CONFIG/);
});

test("08 correction history keeps matrix values aligned to record positions", async () => {
  const source = await readFile(matrixUtilsPath, "utf8");

  assert.match(source, /const recordPositionByIndex = new Map/);
  assert.match(source, /recordPositionByIndex\.get\(change\.before\?\.index\)/);
  assert.match(source, /matrix\[delta\.field\]\[beforePosition\] = delta\.before/);
  assert.match(source, /matrix\[delta\.field\]\[afterPosition\] = delta\.after/);
  assert.match(source, /values\[index\] === unset && values\[index - 1\] !== unset/);
});

test("08 correction history applies displayed defaults and nested numeric thresholds", async () => {
  const [settingsSource, matrixSource, matrixUtilsSource] = await Promise.all([
    readFile(settingsPath, "utf8"),
    readFile(matrixPath, "utf8"),
    readFile(matrixUtilsPath, "utf8"),
  ]);

  assert.match(settingsSource, /Object\.fromEntries\(DATE_FIELDS_CONFIG\.map/);
  assert.match(matrixSource, /Object\.fromEntries\(DATE_FIELDS_CONFIG\.map/);
  assert.match(matrixSource, /numericChangeWithinThreshold\(prevVal, val, numThreshold\)/);
  assert.match(matrixUtilsSource, /const numericSignature =/);
  assert.match(matrixUtilsSource, /children\.flatMap/);
});

test("08 correction history surfaces backend input errors", async () => {
  const source = await readFile(pagePath, "utf8");

  assert.match(source, /throw new Error\(data\.detail \|\| "변동 기록을 불러오지 못했습니다\."\)/);
  assert.match(source, /throw new Error\(data\.detail \|\| "상세 변동 기록을 불러오지 못했습니다\."\)/);
});

test("numbered workflow groups render zero-padded stage numbers", async () => {
  const source = await readFile(sidebarPath, "utf8");

  assert.match(source, /group\.numbered/);
  assert.match(source, /String\(tab\.step\)\.padStart\(2, "0"\)/);
});
