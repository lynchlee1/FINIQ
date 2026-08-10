import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";
const inspectionPanelPath = "frontend/finiq_GUI/apps/market-desk/src/components/data-integrity/DataIntegrityInspectionPanel.tsx";
const inspectionHookPath = "frontend/finiq_GUI/apps/market-desk/src/hooks/useDataIntegrityInspection.ts";
const downloadApiPath = "frontend/finiq_GUI/apps/market-desk/src/features/download/api.ts";
const globalsPath = "frontend/finiq_GUI/apps/market-desk/src/app/globals.css";

test("download review is separate from search conditions and its pending step owns the inspection action", async () => {
  const [source, panel] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionPanelPath, "utf8"),
  ]);
  const searchCardStart = source.indexOf("<DisclosureSearchConditionCard");
  const reviewCardStart = source.indexOf("기존 데이터 검토");
  const searchCardClose = source.indexOf("          />", searchCardStart);

  assert.ok(searchCardStart >= 0);
  assert.ok(searchCardClose > searchCardStart);
  assert.ok(reviewCardStart > searchCardClose);
  assert.doesNotMatch(source.slice(searchCardStart, searchCardClose), /DataIntegrityInspectionPanel/);
  assert.match(source, /<CardTitle[^>]*>[\s\S]*기존 데이터 검토/);
  assert.match(source, /key: "files"[\s\S]{0,3500}label: isCurrentInspectionRunning \? "검사 중\.\.\." : "검사하기"/);
  assert.ok(source.indexOf("label: isCurrentInspectionRunning") < source.indexOf('key: "kind-count"'));
  assert.match(panel, /\{step\.action \? \([\s\S]{0,500}step\.action\.label/);
  assert.doesNotMatch(source, /업데이트 기간 적용/);
  assert.doesNotMatch(source, /폴더 검사하기/);
  assert.match(source, /작업 실행[\s\S]{0,500}md:grid-cols-3/);
});

test("shared integrity panel presents a verdict, ordered steps and failure-only detail", async () => {
  const [source, panel] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionPanelPath, "utf8"),
  ]);

  assert.match(panel, /export type DataIntegrityInspectionStepStatus = "complete" \| "failed" \| "ready" \| "waiting" \| "running"/);
  assert.ok(panel.indexOf("verdict.label") < panel.indexOf("<ol className="));
  assert.match(panel, /\{step\.detail && \(/);
  assert.match(panel, /step\.status === "waiting" \|\| step\.status === "ready" \? index \+ 1/);
  for (const label of ["메타데이터 읽기", "현재 설정과 비교", "저장 파일 구성 검사", "KIND 건수 비교"]) {
    assert.match(source, new RegExp(label));
  }
  assert.match(source, /filterDifferences\.map/);
  assert.match(source, /저장된 설정 적용/);
  assert.match(source, /staleRanges\.map/);
});

test("shared integrity hierarchy stays aligned with the surrounding product UI", async () => {
  const [source, panel] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionPanelPath, "utf8"),
  ]);

  assert.match(panel, /text-\[16px\][^\n]*\{verdict\.title\}/);
  assert.match(panel, /text-\[15px\][^\n]*\{step\.title\}/);
  assert.match(panel, /text-\[13px\][^\n]*\{step\.summary\}/);
  assert.match(source, /CardTitle className="[^"]*text-\[16px\]/);
  assert.doesNotMatch(panel, /text-\[18px\]/);
});

test("shared inspection state ignores stale requests and full verification blocks execution", async () => {
  const [source, hook, api] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(inspectionHookPath, "utf8"),
    readFile(downloadApiPath, "utf8"),
  ]);

  assert.match(source, /useDataIntegrityInspection<DownloadExistingInspectionPayload, DownloadExistingResponse>/);
  assert.match(hook, /setIsChecking\(true\);\s*setError\(null\);/);
  assert.match(hook, /setError\(message\);\s*onErrorRef\.current\?\.\(message\);/);
  assert.match(hook, /requestRef\.current\.id !== requestId \|\| requestRef\.current\.key !== requestKey/);
  assert.match(api, /checkExistingDownload[\s\S]{0,220}verify_with_kind: true/);
  assert.match(source, /const hasVerificationFailure = !verified \|\|/);
  assert.match(source, /if \(candidateCount > 0 \|\| hasVerificationFailure\)/);
  assert.match(source, /if \(existingMetadataError\) \{\s*throw new Error\(existingMetadataError\);/);
  assert.doesNotMatch(hook, /catch \{[\s\S]{0,300}setResult\(null\);/);
});

test("download colored status surfaces use contrast text tokens", async () => {
  const source = await readFile(inspectionPanelPath, "utf8");
  const globals = await readFile(globalsPath, "utf8");

  for (const token of ["--tv-up-text", "--tv-down-text", "--tv-warning-text"]) {
    assert.match(globals, new RegExp(`${token}: #[0-9a-fA-F]{6};`));
  }

  assert.doesNotMatch(source, /bg-\[var\(--tv-(?:up|down|warning)-soft\)\][^"\n]*text-\[var\(--tv-(?:up|down|warning)\)\]/);
  assert.match(source, /warning: "border-\[color:var\(--tv-warning\)\] bg-\[var\(--tv-warning-soft\)\] text-\[var\(--tv-warning-text\)\]"/);
  assert.match(source, /error: "border-\[color:var\(--tv-down\)\] bg-\[var\(--tv-down-soft\)\] text-\[var\(--tv-down-text\)\]"/);
});
