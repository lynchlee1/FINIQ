import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync(
  "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx",
  "utf8",
);

test("external HTML compression only displays successful metadata verification", () => {
  assert.match(page, /res\.metadata_check/);
  assert.match(page, /metadata 확인/);
  assert.doesNotMatch(page, /metadata 누락/);
  assert.doesNotMatch(page, /res\.warnings\.map/);
});
