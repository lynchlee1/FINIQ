import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/dart-link/page.tsx";
const navigationPath = "frontend/finiq_GUI/apps/market-desk/src/config/navigation.ts";
const terminologyPath = "docs/ui-terminology.md";

test("KIND-DART link page is available from disclosure navigation", async () => {
  const [navigation, terminology] = await Promise.all([
    readFile(navigationPath, "utf8"),
    readFile(terminologyPath, "utf8"),
  ]);

  assert.match(navigation, /href: "\/dart-link", step: 5, label: "KIND-DART 연결"/);
  assert.match(terminology, /\| KIND to DART link workflow \| KIND-DART 연결 \|/);
});

test("KIND-DART link page runs the existing background workflow without persisting credentials", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.match(page, /pollingEndpoint: "\/api\/disclosures\/dart-links\/jobs\/\{jobId\}"/);
  assert.match(page, /cancelEndpoint: "\/api\/disclosures\/dart-links\/cancel"/);
  assert.match(page, /"\/api\/disclosures\/dart-links\/build\/start"/);
  assert.match(page, /data_root: dataRoot/);
  assert.match(page, /dart_api_key: dartApiKey/);
  assert.match(page, /type="password"/);
  assert.match(page, /setDartApiKey\(""\)/);
  assert.doesNotMatch(page, /saveSetting\([^\n]*dart/i);
  assert.doesNotMatch(page, /localStorage|sessionStorage/);
});

test("KIND-DART link page shows canonical paths and every matcher outcome", async () => {
  const page = await readFile(pagePath, "utf8");

  assert.match(page, /01-list\/dart-links/);
  assert.match(page, /02-table의 유효한 SQLite manifest/);
  assert.match(page, /DART 원문은 저장하지 않습니다/);
  for (const label of ["연결 완료", "DART 공시 없음 확인", "확인 불가", "후보 중복", "조회 실패"]) {
    assert.match(page, new RegExp(label));
  }
  assert.doesNotMatch(page, /bg-gradient|rounded-(?:2xl|3xl)|shadow-(?:xl|2xl)/);
});
