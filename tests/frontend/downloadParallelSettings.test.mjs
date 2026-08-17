import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync(
  "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx",
  "utf8",
);
const types = fs.readFileSync(
  "frontend/finiq_GUI/apps/market-desk/src/features/download/types.ts",
  "utf8",
);
const store = fs.readFileSync(
  "frontend/finiq_GUI/apps/market-desk/src/store/useSettingsStore.ts",
  "utf8",
);

test("download settings expose both bounded parallel strategies", () => {
  assert.match(page, /SETTINGS_LABELS\.parallelStrategy/);
  assert.match(page, /label: "연도별 병렬"/);
  assert.match(page, /label: "한 연도 내 병렬"/);
  assert.match(page, /<HtmlInspectorField label=\{SETTINGS_LABELS\.parallelStrategy\}>/);
  assert.doesNotMatch(page, /여러 연도 병렬 처리/);
  assert.doesNotMatch(page, /한 연도 내 페이지 병렬 처리/);
  assert.match(page, /parallel_strategy: parallelStrategy/);
  assert.match(types, /parallel_strategy: "years" \| "pages"/);
});

test("download settings persist terminal job retention with a 60 minute default", () => {
  assert.match(page, /작업 기록 보관 시간 \(분\)/);
  assert.match(page, /saveSetting\("job_retention_minutes", normalized\)/);
  assert.match(store, /job_retention_minutes: 60/);
});

test("download market defaults and restores to the full market", () => {
  assert.match(page, /useState\("전체"\)/);
  assert.match(page, /saved\.market_label \|\| "전체"/);
  assert.match(page, /setMarketLabel\(saved\.market_label \|\| "전체"\)/);
  assert.doesNotMatch(page, /검색대상/);
});
