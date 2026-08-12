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
  assert.match(sources[1], /title: "해시와 폴더 구성 검사"/);
  assert.match(sources[2], /stepTitle="입력 HTML과 목차 구성 검사"/);
  assert.match(sources[3], /"\/api\/disclosures\/html\/parse\/inspect"/);
});

test("existing-data inspections start only from explicit actions", async () => {
  const [download, htmlDownload] = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(paths.htmlDownload, "utf8"),
  ]);

  assert.doesNotMatch(download, /checkExisting\(outputDirectory\)/);
  assert.doesNotMatch(download, /runExistingInspection/);
  assert.match(download, /onClick: handleInspectFolder/);
  assert.match(download, /label: "대기"[\s\S]{0,250}title: "검사를 시작하지 않았습니다"/);

  assert.doesNotMatch(htmlDownload, /setTimeout\(\(\) => \{\s*checkExisting\(\)/);
  assert.doesNotMatch(htmlDownload, /자동 병렬 확인 중/);
  assert.match(htmlDownload, /const handleInspectFolder = async \(\) =>/);
  assert.match(htmlDownload, /fetch\(variantConfig\.checkExistingEndpoint/);
  assert.match(htmlDownload, /onClick: handleInspectFolder/);
});

test("HTML inspection uses the workspace output when separate output is disabled", async () => {
  const htmlDownload = await readFile(paths.htmlDownload, "utf8");

  assert.match(htmlDownload, /if \(useSeparateOutputDirectory && !outputDirectory\)/);
  assert.match(
    htmlDownload,
    /const hasInspectionInput = !!currentSourcePath && \(!useSeparateOutputDirectory \|\| !!outputDirectory\)/,
  );
  assert.doesNotMatch(htmlDownload, /if \(!outputDirectory\) \{/);
  assert.match(htmlDownload, /action: hasInspectionInput && !existingCheckCompleted \? \{/);
  assert.equal(htmlDownload.match(/onClick: handleInspectFolder/g)?.length, 1);
  assert.doesNotMatch(htmlDownload, /폴더 검사하기/);
  assert.match(
    htmlDownload,
    /notificationTone=\{isErrorStatus \? "error" : existingCheckError \|\| integrityProblemCount > 0 \? "warning" : "success"\}/,
  );
  assert.doesNotMatch(htmlDownload, /description: existingCheckError \|\| existingDetail/);
  assert.match(htmlDownload, /\{existingData\.output_directory\}/);
});

test("integrity responses stay bound to the inputs that started them", async () => {
  const [download, filter, htmlDownload, table, htmlParse] = await Promise.all([
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/download/page.tsx", "utf8"),
    readFile(paths.filter, "utf8"),
    readFile(paths.htmlDownload, "utf8"),
    readFile("frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx", "utf8"),
    readFile(paths.htmlParse, "utf8"),
  ]);

  assert.match(download, /activeInspection\.key === currentKey[\s\S]{0,120}setExistingMetadataError\(error\.message\)/);
  assert.match(filter, /action: "inspect"/);
  assert.match(filter, /if \(!isCurrentPresetWorkspace\(dataRoot, requestId\)\) return;/);
  assert.match(htmlDownload, /inspectAbortControllerRef\.current\?\.abort\(\);[\s\S]{0,120}setInspectRunning\(false\)/);
  assert.match(table, /context\.key !== currentInspectionKeyRef\.current/);
  assert.match(htmlParse, /context\.key !== currentParseInspectionKeyRef\.current/);
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
  assert.match(source, /inputDirectory, useSeparateOutputDirectory, workers/);
  assert.match(source, /const \[integrityInspectionError, setIntegrityInspectionError\] = useState\(""\)/);
  assert.match(source, /integrityInspectionError[\s\S]{0,100}\? "failed"/);
  assert.match(source, /onClick: inspectExistingData/);
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
