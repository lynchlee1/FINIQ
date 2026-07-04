import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const storePath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/store/useSettingsStore.ts");
const topbarPath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/components/layout/Topbar.tsx");

test("market desk stores runtime parallel worker count in temporary settings state", async () => {
  const source = await readFile(storePath, "utf8");

  assert.match(source, /parallel_worker_count: number/);
  assert.match(source, /runtime_info_loaded: boolean/);
  assert.match(source, /fetchRuntimeInfo: \(\) => Promise<any>/);
  assert.match(source, /parallel_worker_count: Number\(config\.parallel_worker_count \|\| 1\)/);
  assert.match(source, /"parallel_worker_count" \| "runtime_info_loaded"/);
});

test("topbar loads runtime info once when the app shell mounts", async () => {
  const source = await readFile(topbarPath, "utf8");

  assert.match(source, /const \{ fetchRuntimeInfo \} = useSettingsStore\(\)/);
  assert.match(source, /fetchRuntimeInfo\(\)/);
});
