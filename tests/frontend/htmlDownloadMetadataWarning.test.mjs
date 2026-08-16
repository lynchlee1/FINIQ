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

test("HTML reuse without a hash baseline is blocked and reported once", () => {
  // Unverified files still block the run; they are never silently reused.
  assert.match(page, /hash_unverified_target_html_count/);
  assert.match(page, /기준 해시 없음/);

  // The verdict lives only in the inspection card. The data-path card shows
  // paths, so the same failure is not rendered twice.
  assert.match(page, /SingleCheckDataIntegrityInspectionCard/);
  assert.doesNotMatch(page, /기존 원문 저장 범위 감지됨/);
  assert.doesNotMatch(page, /기준 해시 생성/);
  assert.doesNotMatch(page, /trust_existing_files: true/);
});

test("pending downloads are a separate step that never reddens the verdict", () => {
  // Missing files stay out of the integrity verdict...
  const problemCountStatement = page
    .slice(page.indexOf("const integrityProblemCount"))
    .split(";")[0];
  assert.doesNotMatch(problemCountStatement, /missing_target_html_count/);
  // ...and are reported by their own step under the main check instead.
  assert.match(page, /extraSteps=\{inspectionExtraSteps\}/);
  assert.match(page, /key: "pending-download"/);
  assert.match(page, /statusLabel: pendingStepLabel/);
  assert.match(page, /"다운로드 필요"/);
  // That step drives the shortcut back into the normal download job.
  assert.match(page, /label: "재다운로드",\s*onClick: handleRun/);
  assert.match(page, /action: pendingDownloadCount > 0 \?/);
});

test("internal HTML save uses only the compressed external HTML JSON", () => {
  assert.match(page, /source_compressed_json_path: internalSourceFilePath/);
  assert.doesNotMatch(page, /source_directory:/);
  assert.doesNotMatch(page, /폴더 입력/);
  assert.doesNotMatch(page, /JSON 파일 입력/);
});
