import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx";
const pollingHookPath = "frontend/finiq_GUI/apps/market-desk/src/hooks/useJobPolling.ts";
const downloadApiPath = "frontend/finiq_GUI/apps/market-desk/src/features/download/api.ts";

test("destructive cleanup stays bound to the inspected request", async () => {
  const source = await readFile(downloadPagePath, "utf8");
  const deleteHandler = source.slice(
    source.indexOf("const handleDeleteUnexpectedFiles"),
    source.indexOf("if (loading)"),
  );

  assert.match(source, /cleanupCandidatePayloadRef\.current = completedPayload/);
  assert.match(source, /setCleanupCandidateKey\(completedInspectionKey\)/);
  assert.match(source, /cleanupCandidateKey === currentExistingKey/);
  assert.match(deleteHandler, /const payload = cleanupCandidatePayloadRef\.current/);
  assert.match(deleteHandler, /cleanupCandidateKey !== currentKey/);
  assert.doesNotMatch(deleteHandler, /cleanupCandidatePayloadRef\.current \|\| buildPayload\(\)/);
  assert.match(deleteHandler, /inspectExistingFiles\(false, payload\)/);
  assert.match(source, /const clearCleanupCandidates = useCallback\(\(\) => \{[\s\S]*?setDeleteConfirmed\(false\);[\s\S]*?setDeleteConfirmationText\(""\);/);
});

test("inspection terminal processing owns an immutable job context", async () => {
  const [page, polling, api] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(pollingHookPath, "utf8"),
    readFile(downloadApiPath, "utf8"),
  ]);
  const completedBlock = polling.slice(
    polling.indexOf('if (data.status === "completed")'),
    polling.indexOf('} else if (data.status === "cancelled")'),
  );

  assert.match(page, /type DownloadInspectionContext = \{[\s\S]*?jobId: string;[\s\S]*?payload: DownloadPayload;[\s\S]*?runTriggered: boolean;/);
  assert.match(page, /sessionStorage\.setItem\([\s\S]*?JSON\.stringify\(activeInspection\)/);
  assert.match(page, /completedInspection\.jobId !== jobId/);
  assert.match(page, /startDownloadJob\(completedPayload, jobId\)/);
  assert.ok(
    page.indexOf("await startDownloadJob(completedPayload, jobId)")
      < page.indexOf("clearActiveInspection(completedInspection)", page.indexOf("await startDownloadJob(completedPayload, jobId)")),
  );
  assert.match(api, /startDownload\(payload: DownloadPayload, inspectionJobId\?: string\)/);
  assert.match(api, /inspectionJobId \? \{ inspection_job_id: inspectionJobId \} : \{\}/);
  assert.ok(completedBlock.indexOf("await onSuccess") < completedBlock.indexOf("setActiveJobId(null)"));
  assert.match(completedBlock, /activeJobIdRef\.current === jobId/);
  assert.match(completedBlock, /forgetJobId\(jobId\)/);
});

test("reload restores the inspection payload paired with the restored job", async () => {
  const [source, polling] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(pollingHookPath, "utf8"),
  ]);

  assert.match(source, /readStoredInspectionContext/);
  assert.match(source, /sessionStorage\.getItem\(DOWNLOAD_INSPECTION_STORAGE_KEY\)/);
  assert.match(source, /useRef<DownloadInspectionContext \| null>\(readStoredInspectionContext\(\)\)/);
  assert.match(source, /const completedPayload = completedInspection\.payload/);
  assert.match(polling, /const \[isPollingRestored, setIsPollingRestored\] = useState\(false\)/);
  assert.match(polling, /setIsPollingRestored\(true\)/);
  assert.match(source, /if \(isPollingRestored && !loading && !activeJobId && activeInspection\?\.jobId\)/);
  assert.match(source, /await startDownloadJob\(completedPayload, jobId\)[\s\S]{0,300}clearActiveInspection\(completedInspection\)/);
});

test("transient polling failures keep the active job and retry it", async () => {
  const source = await readFile(pollingHookPath, "utf8");
  const catchBlock = source.slice(
    source.indexOf("} catch (err: any) {"),
    source.indexOf("    },\n    [forgetJobId]"),
  );
  const notFoundBlock = catchBlock.slice(
    catchBlock.indexOf("err instanceof ApiError && err.status === 404"),
    catchBlock.indexOf("const { pollInterval = 1000 }"),
  );
  const transientBlock = catchBlock.slice(catchBlock.indexOf("const { pollInterval = 1000 }"));

  assert.match(notFoundBlock, /setActiveJobId\(null\)/);
  assert.doesNotMatch(transientBlock, /setActiveJobId\(null\)/);
  assert.match(transientBlock, /activeJobIdRef\.current === jobId/);
  assert.match(transientBlock, /pollJob\(jobId\)/);
});

test("replaced jobs ignore late polling responses and errors", async () => {
  const source = await readFile(pollingHookPath, "utf8");

  assert.match(
    source,
    /const data = await apiGet<JobSnapshot<any>>\(url\);\s+if \(!mountedRef\.current \|\| activeJobIdRef\.current !== jobId\) return;/,
  );
  assert.match(
    source,
    /} catch \(err: any\) \{\s+if \(!mountedRef\.current \|\| activeJobIdRef\.current !== jobId\) return;/,
  );
});

test("job polling distinguishes a responsive status API from silent work", async () => {
  const source = await readFile(pollingHookPath, "utf8");

  assert.match(source, /const LONG_PROGRESS_SILENCE_SECONDS = 10/);
  assert.match(source, /data\.elapsed_seconds/);
  assert.match(source, /data\.progress_idle_seconds >= LONG_PROGRESS_SILENCE_SECONDS/);
  assert.match(source, /진행 확인: 상태 조회 정상/);
  assert.match(source, /새 로그 \$\{idle\}째 없음/);
});

test("download inspection errors are created only by explicit inspection work", async () => {
  const source = await readFile(downloadPagePath, "utf8");

  const metadataHandler = source.slice(
    source.indexOf("const handleInspectMetadata"),
    source.indexOf("const handleInspectFiles"),
  );
  assert.doesNotMatch(source, /metadataNotificationError|checkingExisting/);
  assert.match(metadataHandler, /detectExistingDownload/);
  assert.match(metadataHandler, /setExistingMetadataError\(err\.message\)/);
  assert.match(metadataHandler, /metadataInspectionRequestIdRef\.current !== requestId \|\| currentMetadataKeyRef\.current !== metadataKey/);
  assert.match(source, /isErrorStatus \|\| !!existingMetadataError/);
});
