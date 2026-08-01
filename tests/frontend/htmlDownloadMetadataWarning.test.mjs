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

test("HTML reuse requires a hash baseline or explicit trust", () => {
  assert.match(page, /hash_unverified_target_html_count/);
  assert.match(page, /현재 외부 HTML 신뢰/);
  assert.match(page, /현재 내부 HTML 신뢰/);
  assert.match(page, /기준 해시 생성/);
  assert.match(page, /external-html-download\/trust-existing\/start/);
  assert.match(page, /internal-html-download\/trust-existing\/start/);
  assert.match(page, /trust_existing_files: true/);
});
