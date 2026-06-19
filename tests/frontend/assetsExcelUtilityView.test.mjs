import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const viewPath = "frontend/finiq_GUI/apps/market-desk/src/features/assets-excel/AssetExcelUtilityView.tsx";

test("duplicate cleanup jobs use the latest recursive scan setting", async () => {
  const source = await readFile(viewPath, "utf8");

  assert.match(source, /const duplicateScanRecursiveRef = useRef\(false\);/);
  assert.match(source, /duplicateScanRecursiveRef\.current = value;/);
  assert.match(source, /scan_recursive: duplicateScanRecursiveRef\.current,/);
});
