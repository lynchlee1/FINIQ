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

test("the inspection action is numbered and pending downloads are an unnumbered bundled result", () => {
  // Missing files stay out of the integrity verdict...
  const problemCountStatement = page
    .slice(page.indexOf("const integrityProblemCount"))
    .split(";")[0];
  assert.doesNotMatch(problemCountStatement, /missing_target_html_count/);
  // ...and are reported by their own result row under the main check instead.
  assert.match(page, /extraSteps=\{showSaveWorkflow \? inspectionExtraSteps : undefined\}/);
  assert.match(page, /key: "pending-download",\s*numbered: false/);
  assert.doesNotMatch(page, /<SingleCheckDataIntegrityInspectionCard[\s\S]{0,250}numbered=\{false\}/);
  assert.match(page, /const pendingStepStatus = inspectRunning\s*\? "waiting"/);
  assert.match(page, /const pendingStepLabel = inspectRunning\s*\? "대기"/);
  assert.doesNotMatch(page, /const pendingStepStatus = inspectRunning\s*\? "running"/);
  assert.match(page, /statusLabel: pendingStepLabel/);
  assert.match(page, /setExistingData\(data\)/);
  assert.doesNotMatch(page, /setExistingData\(data\.has_existing \? data : null\)/);
  assert.match(page, /"다운로드 필요"/);
  assert.doesNotMatch(problemCountStatement, /compressionInspectionData/);
  assert.match(page, /const existingDataInspectionCard = \(\s*<SingleCheckDataIntegrityInspectionCard/);
  // That step drives the shortcut back into the normal download job.
  assert.match(page, /label: "재다운로드",\s*onClick: handleRun/);
  assert.match(page, /action: !inspectRunning && pendingDownloadCount > 0 && !selectedFilterParentMode \?/);
});

test("switching to compression resets inspection and checks the compressed JSON", () => {
  assert.match(
    page,
    /\[currentSourcePath, dataRoot, selectedFilterId, limit, problemFileLimit, externalTaskMode\]/,
  );
  assert.match(page, /const compressionInspectionCopy = \{/);
  assert.match(page, /"압축 파일에 문제가 있습니다"/);
  assert.match(page, /compressed-external-html\.json의 형식, 현재 필터 대상 기록, 원문 hash·size 일치 여부/);
  assert.match(page, /"\/api\/disclosures\/external-html-download\/compress\/check-existing"/);
  assert.match(page, /onClick: isExternalCompressMode \? handleInspectCompressedFile : handleInspectFolder/);
  assert.match(page, /const inspectionCopy = isExternalCompressMode\s*\? compressionInspectionCopy\s*:\s*saveInspectionCopy/);
  assert.match(page, /stepTitle=\{isExternalCompressMode \? "압축 파일 검사" : "기존 원문 데이터 검사"\}/);
  assert.match(page, /const inspectionStepSummary = isExternalCompressMode\s*\? compressionInspectionStepSummary\s*:\s*saveInspectionStepSummary/);
});

test("internal HTML save derives its compressed source from the workspace mode", () => {
  assert.match(page, /const currentSourcePath = dataRoot/);
  assert.match(page, /output_directory: ""/);
  assert.doesNotMatch(page, /source_compressed_json_path:/);
  assert.doesNotMatch(page, /source_directory:/);
  assert.doesNotMatch(page, /폴더 입력/);
  assert.doesNotMatch(page, /JSON 파일 입력/);
});
