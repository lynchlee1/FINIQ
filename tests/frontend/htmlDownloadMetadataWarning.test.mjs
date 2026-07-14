import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync(
  "frontend/finiq_GUI/apps/market-desk/src/app/html-download/_components/HtmlDownloadPageView.tsx",
  "utf8",
);

test("external HTML compression displays missing metadata warnings", () => {
  assert.match(page, /res\.metadata_check/);
  assert.match(page, /metadata 누락/);
  assert.match(page, /res\.warnings\.map/);
  assert.match(page, /`경고: \$\{String\(warning\)\}`/);
});
