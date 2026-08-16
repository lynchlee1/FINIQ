import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const tablePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx";
const nextConfigPath = "frontend/finiq_GUI/apps/market-desk/next.config.js";

test("market desk proxy allows the table integrity inspection to finish", async () => {
  const source = await readFile(nextConfigPath, "utf8");

  assert.match(source, /proxyTimeout: 10 \* 60 \* 1000/);
});

test("table page puts the shared existing-data review before path and execution settings", async () => {
  const source = await readFile(tablePagePath, "utf8");
  const reviewStart = source.indexOf("<SingleCheckDataIntegrityInspectionCard");
  const pathCardStart = source.indexOf("<DataPathCard");
  const executionCardStart = source.indexOf(">작업 실행</CardTitle>");

  assert.ok(reviewStart >= 0);
  assert.ok(pathCardStart > reviewStart);
  assert.ok(executionCardStart > pathCardStart);
  assert.match(source, /useDataIntegrityInspection<TableInspectionPayload, TableInspectionResult>/);
  assert.match(source, /"\/api\/disclosures\/table\/inspect"/);
  assert.match(source, /stepTitle="원본 데이터와 변환 결과 검사"/);
  assert.match(source, /다운로드한 원본 데이터와 변환 기록, 연도별 SQLite 파일의 내용이 서로 일치하는지 확인합니다/);
  assert.doesNotMatch(source, /매니페스트|SQLite shard|연도 샤드|연도 shard|레코드/);
  assert.match(source, /label: inspectionRunning \? "검사 중\.\.\." : "검사하기"/);
  assert.match(source, /type SingleCheckDataIntegrityInspectionState/);
  assert.match(source, /activeBuildInspectionRef/);
  assert.match(source, /context\.key !== currentInspectionKeyRef\.current/);
});
