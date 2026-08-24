import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const paths = {
  filter: "frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx",
  htmlDownload: "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx",
  sectionSplit: "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx",
  htmlParse: "frontend/finiq_GUI/apps/market-desk/src/app/html-parse/page.tsx",
};
const cardPath = "frontend/finiq_GUI/apps/market-desk/src/components/data-integrity/DataIntegrityInspectionCard.tsx";
const panelPath = "frontend/finiq_GUI/apps/market-desk/src/components/data-integrity/DataIntegrityInspectionPanel.tsx";
const hookPath = "frontend/finiq_GUI/apps/market-desk/src/hooks/useDataIntegrityInspection.ts";

test("numbered disclosure pages reuse the shared integrity card", async () => {
  const [sources, card] = await Promise.all([
    Promise.all(Object.values(paths).map((path) => readFile(path, "utf8"))),
    readFile(cardPath, "utf8"),
  ]);

  for (const source of sources) {
    assert.match(source, /DataIntegrityInspectionCard/);
    assert.match(source, /<(?:SingleCheck)?DataIntegrityInspectionCard/);
  }
  assert.match(card, /success: \{ label: "정상"/);
  assert.match(card, /failed: \{ label: "사용 불가"/);
  assert.match(card, /waiting: \{ label: "대기"[\s\S]*stepLabel: "대기"/);
  assert.match(card, /ready: \{ label: "대기"[\s\S]*stepStatus: "waiting"[\s\S]*stepLabel: "대기"/);

  assert.match(sources[0], /listDisclosureConditionPresets\(rootDirectory\)/);
  assert.match(sources[1], /stepTitle=\{isExternalCompressMode \? "압축 파일 검사" : "기존 원문 데이터 검사"\}/);
  assert.match(sources[2], /stepTitle="입력 HTML과 목차 구성 검사"/);
  assert.match(sources[3], /"\/api\/disclosures\/html\/parse\/inspect"/);
});

test("bundled inspection numbers the action row and leaves result-only rows blank", async () => {
  const [download, htmlDownload, panel] = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(paths.htmlDownload, "utf8"),
    readFile(panelPath, "utf8"),
  ]);

  assert.match(panel, /numbered\?: boolean/);
  assert.match(panel, /const stepNumber = step\.numbered === false \? null : \+\+sequenceNumber/);
  assert.match(panel, /step\.numbered === false && step\.status === "running"\s*\? "waiting"/);
  assert.match(panel, /stepDisplayStatus === "waiting" \|\| stepDisplayStatus === "ready" \? stepNumber/);
  assert.match(htmlDownload, /const inspectionExtraSteps: DataIntegrityInspectionStep\[\] = variant === "internal" \? \[\{/);
  assert.match(htmlDownload, /key: "pending-download",\s*numbered: false/);
  assert.match(download, /key: "kind-count",\s*numbered: false/);
  assert.doesNotMatch(htmlDownload, /<SingleCheckDataIntegrityInspectionCard[\s\S]{0,250}numbered=\{false\}/);
  assert.match(htmlDownload, /\? handleInspectCompressedFile\s*: handleInspectFolder/);
  assert.doesNotMatch(htmlDownload, /key: "rebuild-all-compression"/);
});

test("existing-data inspections start only from explicit actions", async () => {
  const [download, htmlDownload] = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(paths.htmlDownload, "utf8"),
  ]);

  assert.doesNotMatch(download, /checkExisting\(outputDirectory\)/);
  assert.doesNotMatch(download, /runExistingInspection/);
  assert.match(download, /onClick: handleInspectMetadata/);
  assert.match(download, /label: "대기"[\s\S]{0,250}title: "검사를 시작하지 않았습니다"/);

  assert.doesNotMatch(htmlDownload, /setTimeout\(\(\) => \{\s*checkExisting\(\)/);
  assert.doesNotMatch(htmlDownload, /자동 병렬 확인 중/);
  assert.match(htmlDownload, /const handleInspectFolder = async \(\) =>/);
  assert.match(htmlDownload, /fetch\(variantConfig\.checkExistingEndpoint/);
  assert.match(htmlDownload, /\? handleInspectCompressedFile\s*: handleInspectFolder/);
});

test("stage 05 through 07 keep existing-data review above workflow inputs", async () => {
  const [htmlDownload, sectionSplit, htmlParse] = await Promise.all([
    readFile(paths.htmlDownload, "utf8"),
    readFile(paths.sectionSplit, "utf8"),
    readFile(paths.htmlParse, "utf8"),
  ]);

  assert.ok(
    htmlDownload.indexOf("{existingDataInspectionCard}")
      < htmlDownload.indexOf('<CardTitle className="dark:text-white">조건검색 필터</CardTitle>'),
  );
  assert.ok(
    sectionSplit.indexOf("<SingleCheckDataIntegrityInspectionCard")
      < sectionSplit.indexOf('<CardTitle className="dark:text-white">조건검색 필터</CardTitle>'),
  );
  assert.ok(
    htmlParse.indexOf("<SingleCheckDataIntegrityInspectionCard")
      < htmlParse.indexOf('<CardTitle className="dark:text-white">변환 설정</CardTitle>'),
  );
});

test("HTML inspection always derives its mode-owned paths from the workspace", async () => {
  const htmlDownload = await readFile(paths.htmlDownload, "utf8");

  assert.match(htmlDownload, /const currentSourcePath = dataRoot/);
  assert.match(htmlDownload, /output_directory: ""/);
  assert.match(htmlDownload, /const hasInspectionInput = !!currentSourcePath/);
  assert.doesNotMatch(htmlDownload, /useSeparateOutputDirectory/);
  assert.match(htmlDownload, /action=\{hasInspectionInput \? \{/);
  assert.match(htmlDownload, /\? handleInspectCompressedFile\s*: handleInspectFolder/);
  assert.doesNotMatch(htmlDownload, /폴더 검사하기/);
  assert.match(htmlDownload, /notificationTone=\{isErrorStatus \? "error" : existingCheckError \|\| integrityProblemCount > 0 \|\| remainingInspection \|\| externalSaveInspectionFailed \|\| compressionInspectionFailed \? "warning" : "success"\}/);
  assert.doesNotMatch(htmlDownload, /description: existingCheckError \|\| existingDetail/);
  assert.match(htmlDownload, /\{existingData\.output_directory\}/);
});

test("HTML problem-file notices require visible confirmation and limit details", async () => {
  const htmlDownload = await readFile(paths.htmlDownload, "utf8");

  assert.match(htmlDownload, /useState\("20"\)/);
  assert.match(htmlDownload, /label: "문제 파일 표시 수"/);
  assert.match(htmlDownload, /parsedProblemFileLimit/);
  assert.match(htmlDownload, /problem_file_limit: parsedProblemFileLimit/);
  assert.match(htmlDownload, /notificationDismissible=\{false\}/);
  assert.match(htmlDownload, /Label htmlFor="deleteConfirmationText"[\s\S]*확인 문구/);
  assert.match(htmlDownload, /확인했습니다\.&quot;를 정확히 입력하고 삭제 허가를 선택하세요/);
  assert.match(htmlDownload, /deleteConfirmed && deleteConfirmationText\.trim\(\) === "확인했습니다\." && \(/);
  assert.doesNotMatch(htmlDownload, /JSON\.stringify\(lastInspectionResult/);
  assert.match(htmlDownload, /나머지 \{formatInteger\(omittedProblemFileCount\)\}개는 표시하지 않았습니다/);
});

test("completed disclosure inspections reuse their result control for another inspection", async () => {
  const [download, filter, htmlDownload, table, sectionSplit, htmlParse, panel] = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(paths.filter, "utf8"),
    readFile(paths.htmlDownload, "utf8"),
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx", "utf8"),
    readFile(paths.sectionSplit, "utf8"),
    readFile(paths.htmlParse, "utf8"),
    readFile(panelPath, "utf8"),
  ]);

  assert.match(download, /action: outputDirectory \? \{/);
  assert.match(filter, /action: rootDirectory\?\.trim\(\) \? \{/);
  assert.match(htmlDownload, /action=\{hasInspectionInput \? \{/);
  assert.match(table, /action=\{hasInspectionInput \? \{/);
  assert.match(sectionSplit, /action=\{hasInspectionInput \? \{/);
  assert.match(htmlParse, /action=\{hasInspectionInput \? \{/);
  for (const source of [download, filter, table, sectionSplit, htmlParse]) {
    assert.match(source, /showResultStatus: true/);
  }
  assert.match(htmlDownload, /showResultStatus: !\(externalSaveRedownloadable[\s\S]{0,100}isExternalCompressMode && compressionInspectionRepairable/);
  assert.match(download, /const metadataResultStatus = existingMetadataError[\s\S]*status: "complete" as const, label: "정상"/);
  assert.match(download, /const filesResultStatus = fileInspectionError \|\| inspectionCandidates\.length > 0[\s\S]*status: "failed" as const, label: "사용 불가"/);
  assert.match(download, /resultStatus: isMetadataRunning \? undefined : metadataResultStatus/);
  assert.match(download, /resultStatus: isFileInspectionRunning \? undefined : filesResultStatus/);
  assert.match(panel, /const displayedStatus = resultStatus\?\.status \?\? step\.status/);
  assert.match(panel, /const displayedStatusLabel = resultStatus\?\.label \?\? step\.statusLabel/);
  assert.match(panel, /aria-label=\{showResultStatus \? `\$\{displayedStatusLabel\}, 검사하기` : undefined\}/);
});

test("filter inspection ignores responses invalidated by preset mutations", async () => {
  const filter = await readFile(paths.filter, "utf8");

  assert.match(filter, /const inspectionRequestIdRef = useRef\(0\)/);
  assert.match(filter, /const inspectionRequestId = \+\+inspectionRequestIdRef\.current/);
  assert.match(filter, /inspectionRequestIdRef\.current !== inspectionRequestId/);
  assert.match(filter, /setPresets\(saved\.presets\);\s+inspectionRequestIdRef\.current \+= 1;\s+setInspectionRunning\(false\)/);
  assert.match(filter, /setPresets\(response\.presets\);\s+inspectionRequestIdRef\.current \+= 1;\s+setInspectionRunning\(false\)/);
});

test("integrity responses stay bound to the inputs that started them", async () => {
  const [download, filter, htmlDownload, table, htmlParse] = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(paths.filter, "utf8"),
    readFile(paths.htmlDownload, "utf8"),
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx", "utf8"),
    readFile(paths.htmlParse, "utf8"),
  ]);

  assert.match(download, /activeInspection\.key === currentKey[\s\S]{0,120}setFileInspectionError\(error\.message\)/);
  assert.match(download, /metadataInspectionRequestIdRef\.current !== requestId \|\| currentMetadataKeyRef\.current !== metadataKey/);
  assert.match(filter, /action: "inspect"/);
  assert.match(filter, /if \(!isCurrentPresetWorkspace\(dataRoot, requestId\)\) return;/);
  assert.match(htmlDownload, /inspectAbortControllerRef\.current\?\.abort\(\);[\s\S]{0,120}setInspectRunning\(false\)/);
  assert.match(table, /context\.key !== currentInspectionKeyRef\.current/);
  assert.match(htmlParse, /context\.key !== currentParseInspectionKeyRef\.current/);
});

test("changing a main or detail page immediately cancels its running inspection", async () => {
  const [download, filter, htmlDownload, hook, design] = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(paths.filter, "utf8"),
    readFile(paths.htmlDownload, "utf8"),
    readFile(hookPath, "utf8"),
    readFile("design/components/inspection-block.md", "utf8"),
  ]);

  assert.match(hook, /inspect: \(payload: TPayload, signal: AbortSignal\)/);
  assert.match(hook, /useEffect\(\(\) => \(\) => \{\s*abortControllerRef\.current\?\.abort\(\);/);
  assert.match(hook, /const clear = useCallback\(\(\) => \{\s*abortControllerRef\.current\?\.abort\(\);/);
  assert.match(download, /useEffect\(\(\) => \(\) => \{[\s\S]{0,260}cancelDownload\(activeInspection\.jobId\)/);
  assert.match(filter, /inspectionAbortControllerRef\.current\?\.abort\(\);[\s\S]{0,260}\[rootDirectory, taskMode\]/);
  assert.match(htmlDownload, /inspectAbortControllerRef\.current\?\.abort\(\);[\s\S]{0,500}\[currentSourcePath, dataRoot, inspectionFilterKey, inspectionLimitKey, problemFileLimit, externalTaskMode\]/);
  assert.match(design, /다른 메인 페이지로 이동하면 해당 페이지의 모든 진행 중 검사를 즉시 취소/);
  assert.match(design, /`공시원문 외부 저장`의 `외부 HTML 저장`과 `외부 HTML 압축` 전환도 같은 규칙/);
  assert.match(design, /서버 취소 API도 호출/);
});

test("section integrity card uses the full inspection endpoint", async () => {
  const source = await readFile(paths.sectionSplit, "utf8");
  const handler = source.slice(
    source.indexOf("const inspectExistingData"),
    source.indexOf("const inspectFolder"),
  );

  assert.match(handler, /"\/api\/disclosures\/html\/sections\/inspect\/start"/);
  assert.doesNotMatch(handler, /page_size|\/sections\/list/);
  assert.match(handler, /startPolling\(jobId\)/);
  assert.match(source, /activeIntegrityInspectionRef/);
  assert.match(source, /inspectionContext\.key !== currentIntegrityInspectionKeyRef\.current/);
  assert.match(source, /currentFilterMode,[\s\S]{0,160}inputDirectory,[\s\S]{0,120}useSeparateOutputDirectory,[\s\S]{0,80}workers/);
  assert.match(source, /const \[integrityInspectionError, setIntegrityInspectionError\] = useState\(""\)/);
  assert.match(source, /integrityInspectionError[\s\S]{0,100}\? "failed"/);
  assert.match(source, /onClick: inspectExistingData/);
  assert.match(source, /<CardTitle className="dark:text-white">조건검색 필터<\/CardTitle>/);
  assert.match(source, /<FilterPresetCombobox/);
  assert.match(source, /mode: currentFilterMode/);
  assert.match(source, /currentParentMode \? \{ parent_mode: currentParentMode \} : \{\}/);
  assert.match(source, /input_directory: useSeparateOutputDirectory \? inputDirectory : ""/);
  assert.match(source, /const handleFilterInputChange = \(value: string\) => \{[\s\S]*?setInspectResult\(null\)[\s\S]*?setSectionPatterns\(\[\]\)/);
});

test("parse inspection waits for its mode and parser method", async () => {
  const source = await readFile(paths.htmlParse, "utf8");

  assert.match(source, /const hasInspectionInput = !!dataRoot\s*&& !!currentFilterMode\s*&& !!parserMethod/);
  assert.match(source, /if \(!dataRoot \|\| !currentFilterMode \|\| !parserMethod\)/);
  assert.match(source, /모드와 파싱 방법, 경로를 선택하세요/);
});

test("existing-data guidance avoids mechanical Korean phrasing", async () => {
  const sources = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    ...Object.values(paths).map((path) => readFile(path, "utf8")),
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx", "utf8"),
  ]);

  for (const source of sources) {
    assert.doesNotMatch(source, /문제가 확인됐습니다|안전하게 (?:재)?사용할 수 있습니다|검사할 수 있습니다/);
    assert.doesNotMatch(source, /매니페스트|SQLite shard|연도 샤드|연도 shard|레코드/);
  }
  assert.doesNotMatch(sources[0], /label: "검토 중단"/);
  assert.doesNotMatch(sources[1], /\$\{preset\.status\}/);
});
