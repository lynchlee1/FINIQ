import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pollingHookPath = "frontend/finiq_GUI/apps/market-desk/src/hooks/useJobPolling.ts";
const apiTypesPath = "frontend/finiq_GUI/apps/market-desk/src/types/api.ts";

test("HTML download jobs show a ten-second rolling download rate", async () => {
  const [pollingHook, apiTypes] = await Promise.all([
    readFile(pollingHookPath, "utf8"),
    readFile(apiTypesPath, "utf8"),
  ]);

  assert.match(pollingHook, /다운로드 속도: \$\{data\.downloads_per_minute\} download\/min/);
  assert.match(pollingHook, /최근 \$\{data\.download_rate_window_seconds\}초 \$\{data\.recent_download_count\}건/);
  assert.match(apiTypes, /download_rate_window_seconds\?: number/);
  assert.match(apiTypes, /recent_download_count\?: number/);
  assert.match(apiTypes, /downloads_per_minute\?: number/);
});
