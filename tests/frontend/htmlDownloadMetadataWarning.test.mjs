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

test("external and internal save use one repairable inspection row", () => {
  // Missing files stay out of the integrity verdict...
  const problemCountStatement = page
    .slice(page.indexOf("const integrityProblemCount"))
    .split(";")[0];
  assert.doesNotMatch(problemCountStatement, /missing_target_html_count/);
  // ...and switch the existing inspection action to repair instead of adding a row.
  assert.doesNotMatch(page, /extraSteps=/);
  assert.doesNotMatch(page, /key: "pending-download"/);
  assert.doesNotMatch(page, /title: "미저장 원문 다운로드"/);
  assert.match(page, /setAllModeSaveInspectionData\(data\)/);
  assert.doesNotMatch(page, /setExistingData\(data\.has_existing \? data : null\)/);
  assert.doesNotMatch(problemCountStatement, /compressionInspectionData/);
  assert.match(page, /const existingDataInspectionCard = \(\s*<SingleCheckDataIntegrityInspectionCard/);
  assert.match(page, /const saveRedownloadable = showSaveWorkflow && saveRepairTargetCount > 0/);
  assert.match(page, /saveRedownloadable[\s\S]{0,100}\? "재다운로드"/);
  assert.match(page, /saveRedownloadable\s*\? handleRedownloadMissingHtml/);
});

test("switching to compression resets inspection and checks the compressed JSON", () => {
  assert.doesNotMatch(page, /inspectionFilterKey/);
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
  assert.match(page, /compressionInspectionData\?\.skipped_mode_count/);
  assert.match(page, /result\.skipped \? "압축 안 함"/);
  assert.match(page, /원본 HTML이 없어 압축 파일을 검사하거나 생성하지 않습니다/);
  assert.doesNotMatch(page, /key: "rebuild-all-compression"/);
  assert.doesNotMatch(page, /extraSteps=/);
  assert.match(page, /compressionResults\.map/);
  assert.match(page, /\? handleInspectCompressedFile\s*: handleInspectFolder/);
  assert.match(page, /const inspectionCopy = isExternalCompressMode\s*\? compressionInspectionCopy\s*:\s*saveInspectionCopy/);
  assert.match(page, /stepTitle=\{isExternalCompressMode \? "압축 파일 검사" : "기존 원문 데이터 검사"\}/);
  assert.match(page, /const inspectionStepSummary = isExternalCompressMode\s*\? compressionInspectionStepSummary\s*:\s*saveInspectionStepSummary/);
});

test("external HTML save inspection checks every workspace mode", () => {
  assert.match(page, /const \[allModeSaveInspectionData, setAllModeSaveInspectionData\] = useState<any>\(null\)/);
  assert.match(page, /const payload = \{\s*data_root: dataRoot/);
  assert.match(page, /allModeSaveInspectionData\.results[\s\S]{0,100}item\.id === selectedFilterId/);
  assert.match(page, /모든 모드의 대상과 저장 파일을 비교/);
  assert.match(page, /saveInspectionResults\.map/);
  assert.match(page, /미저장 또는 무결성 문제가 있습니다/);
  assert.match(page, /allModeSaveInspectionData\?\.owner_download_required_target_html_count/);
  assert.match(page, /기본 모드 대상 .*owner_requested_count/);
  assert.match(page, /"\/api\/disclosures\/external-html-download\/redownload\/start"/);
  assert.match(page, /const saveRedownloadable = showSaveWorkflow/);
  assert.match(
    page,
    /const saveRepairTargetCount = Number\([\s\S]{0,180}owner_download_required_target_html_count[\s\S]{0,180}owner_hash_unverified_target_html_count/,
  );
  assert.match(page, /saveRepairTargetCount > 0/);
  assert.match(page, /saveRedownloadable\s*\? handleRedownloadMissingHtml/);
  assert.match(page, /saveRedownloadable\s*\? "재다운로드"/);
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

test("internal HTML save uses the same all-mode repair contract", () => {
  assert.match(page, /redownloadEndpoint: "\/api\/disclosures\/internal-html-download\/redownload\/start"/);
  assert.match(page, /"finiq_disclosure_internal_html_redownload_result_v1"/);
  assert.match(page, /setAllModeSaveInspectionData\(nextResult\.verification\)/);
  assert.match(page, /showSaveWorkflow && allModeSaveInspectionData/);
  assert.match(page, /saveInspectionResults\.map/);
  assert.match(page, /KIND 원본 없음/);
  assert.match(page, /source_unavailable_target_html_count/);
  assert.doesNotMatch(page, /variant !== "external" && !selectedFilterPreset/);
  assert.doesNotMatch(page, /inspectionFilterKey|inspectionLimitKey/);
});
