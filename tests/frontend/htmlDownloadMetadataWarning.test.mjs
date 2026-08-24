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

test("external save uses one repairable inspection row and internal save keeps its bundled result", () => {
  // Missing files stay out of the integrity verdict...
  const problemCountStatement = page
    .slice(page.indexOf("const integrityProblemCount"))
    .split(";")[0];
  assert.doesNotMatch(problemCountStatement, /missing_target_html_count/);
  // ...and are reported by their own result row under the main check instead.
  assert.match(page, /extraSteps=\{inspectionExtraSteps\.length \? inspectionExtraSteps : undefined\}/);
  assert.match(page, /const inspectionExtraSteps: DataIntegrityInspectionStep\[\] = variant === "internal" \? \[\{/);
  assert.match(page, /key: "pending-download",\s*numbered: false/);
  assert.doesNotMatch(page, /<SingleCheckDataIntegrityInspectionCard[\s\S]{0,250}numbered=\{false\}/);
  assert.match(page, /const pendingStepStatus = inspectRunning\s*\? "waiting"/);
  assert.match(page, /const pendingStepLabel = inspectRunning\s*\? "대기"/);
  assert.doesNotMatch(page, /const pendingStepStatus = inspectRunning\s*\? "running"/);
  assert.match(page, /statusLabel: pendingStepLabel/);
  assert.match(page, /setExternalSaveInspectionData\(variant === "external" \? data : null\)/);
  assert.doesNotMatch(page, /setExistingData\(data\.has_existing \? data : null\)/);
  assert.match(page, /"다운로드 필요"/);
  assert.doesNotMatch(problemCountStatement, /compressionInspectionData/);
  assert.match(page, /const existingDataInspectionCard = \(\s*<SingleCheckDataIntegrityInspectionCard/);
  // The internal-only result row still drives its selected-mode download job.
  assert.match(page, /label: "재다운로드",\s*onClick: handleRun/);
});

test("switching to compression resets inspection and checks the compressed JSON", () => {
  assert.match(
    page,
    /const inspectionFilterKey = variant === "external" \? "" : selectedFilterId/,
  );
  assert.match(page, /const compressionInspectionCopy = \{/);
  assert.match(page, /"압축 파일에 문제가 있습니다"/);
  assert.match(page, /모든 모드의 compressed-external-html\.json 형식, 저장된 원문 HTML 기록, hash·size 일치 여부/);
  assert.match(page, /"\/api\/disclosures\/external-html-download\/compress\/check-existing"/);
  assert.match(page, /"\/api\/disclosures\/external-html-download\/compress\/repair\/start"/);
  assert.match(page, /\? "재생성"/);
  assert.match(page, /setCompressionInspectionData\(nextResult\.verification\)/);
  assert.match(page, /setCompressionInspectionError\(nextResult\.passed \? "" : "압축 파일 재생성에 실패했습니다\."\)/);
  assert.match(page, /compressionInspectionData\?\.repairable_failed_mode_count/);
  assert.match(page, /compressionInspectionRepairable\s*\? `\$\{formatInteger\(compressionInspectionData\?\.repairable_failed_mode_count/);
  assert.doesNotMatch(page, /key: "rebuild-all-compression"/);
  assert.match(page, /extraSteps=\{inspectionExtraSteps\.length \? inspectionExtraSteps : undefined\}/);
  assert.match(page, /compressionResults\.map/);
  assert.match(page, /\? handleInspectCompressedFile\s*: handleInspectFolder/);
  assert.match(page, /const inspectionCopy = isExternalCompressMode\s*\? compressionInspectionCopy\s*:\s*saveInspectionCopy/);
  assert.match(page, /stepTitle=\{isExternalCompressMode \? "압축 파일 검사" : "기존 원문 데이터 검사"\}/);
  assert.match(page, /const inspectionStepSummary = isExternalCompressMode\s*\? compressionInspectionStepSummary\s*:\s*saveInspectionStepSummary/);
});

test("external HTML save inspection checks every workspace mode", () => {
  assert.match(page, /const \[externalSaveInspectionData, setExternalSaveInspectionData\] = useState<any>\(null\)/);
  assert.match(page, /variant === "external"[\s\S]{0,180}data_root: dataRoot/);
  assert.match(page, /externalSaveInspectionData\.results\.find\(\(item: any\) => item\.id === selectedFilterId\)/);
  assert.match(page, /모든 모드의 대상과 저장 파일을 비교/);
  assert.match(page, /externalSaveResults\.map/);
  assert.match(page, /미저장 또는 무결성 문제가 있습니다/);
  assert.match(page, /externalSaveInspectionData\?\.owner_download_required_target_html_count/);
  assert.match(page, /기본 모드 대상 .*owner_requested_count/);
  assert.match(page, /"\/api\/disclosures\/external-html-download\/redownload\/start"/);
  assert.match(page, /const externalSaveRedownloadable = variant === "external"/);
  assert.match(
    page,
    /const externalSaveRepairTargetCount = Number\([\s\S]{0,180}owner_download_required_target_html_count[\s\S]{0,180}owner_hash_unverified_target_html_count/,
  );
  assert.match(page, /externalSaveRepairTargetCount > 0/);
  assert.match(page, /externalSaveRedownloadable\s*\? handleRedownloadMissingExternalHtml/);
  assert.match(page, /externalSaveRedownloadable\s*\? "재다운로드"/);
  const inspectionAction = page.slice(
    page.indexOf("action={hasInspectionInput ?"),
    page.indexOf("/>\n  );", page.indexOf("action={hasInspectionInput ?")),
  );
  assert.doesNotMatch(inspectionAction, /owner_hash_unverified_target_html_count/);
});

test("internal HTML save derives its compressed source from the workspace mode", () => {
  assert.match(page, /const currentSourcePath = dataRoot/);
  assert.match(page, /output_directory: ""/);
  assert.doesNotMatch(page, /source_compressed_json_path:/);
  assert.doesNotMatch(page, /source_directory:/);
  assert.doesNotMatch(page, /폴더 입력/);
  assert.doesNotMatch(page, /JSON 파일 입력/);
});
