import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";

test("applying saved settings preserves metadata inspection and invalidates only later steps", async () => {
  const source = await readFile(downloadPagePath, "utf8");
  const metadataResetEffect = source.slice(
    source.indexOf("useEffect(() => {\n    clearExistingInspection();"),
    source.indexOf("  useEffect(() => {\n    clearCleanupCandidates();", source.indexOf("useEffect(() => {\n    clearExistingInspection();")),
  );
  const dependentResetEffect = source.slice(
    source.indexOf("  useEffect(() => {\n    clearCleanupCandidates();", source.indexOf("useEffect(() => {\n    clearExistingInspection();")),
    source.indexOf("\n\n  const buildPayload"),
  );
  const applySavedSettings = source.slice(
    source.indexOf("  const handleApplySavedFilters = () =>"),
    source.indexOf("\n\n  const fetchOptions"),
  );

  assert.match(source, /const metadataInspectionKey = \(payload: DownloadExistingPayload\) => JSON\.stringify\(\{\s*output_directory: payload\.output_directory/);
  assert.match(metadataResetEffect, /outputDirectory/);
  assert.doesNotMatch(metadataResetEffect, /companyName|marketLabel|selectedDisclosures/);
  assert.match(dependentResetEffect, /setLastInspectedFilesKey\(null\)/);
  assert.doesNotMatch(dependentResetEffect, /clearExistingInspection|setLastInspectedMetadataKey/);
  assert.match(applySavedSettings, /setCompanyName\(saved\.company_name/);
  assert.doesNotMatch(applySavedSettings, /detectExistingDownload|handleInspectMetadata|clearExistingInspection/);
  assert.match(source, /existingData\.saved_filters_consistent\s*&& areFiltersMatching\(currentFilters, existingData\.saved_filters\)/);
  assert.match(source, /const hasCompletedMetadata = currentMetadataKey === lastInspectedMetadataKey/);
});
