import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-change-log/page.tsx";
const settingsPath = "frontend/finiq_GUI/apps/market-desk/src/components/html-change-log/ChangeLogSettings.tsx";
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

test("numbered workflow groups render zero-padded stage numbers", async () => {
  const source = await readFile(sidebarPath, "utf8");

  assert.match(source, /group\.numbered/);
  assert.match(source, /String\(tab\.step\)\.padStart\(2, "0"\)/);
});
