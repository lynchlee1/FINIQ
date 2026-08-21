import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const filterPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx";
const presetClientPath = "frontend/finiq_GUI/apps/market-desk/src/lib/disclosureConditionPresets.ts";
const conditionCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureConditionFilterCard.tsx";
const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx";
const htmlParsePagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-parse/page.tsx";
const automationPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/disclosure-automation/page.tsx";

test("derived disclosure filters keep parent and child identities separate", async () => {
  const [page, client, card] = await Promise.all([
    readFile(filterPagePath, "utf8"),
    readFile(presetClientPath, "utf8"),
    readFile(conditionCardPath, "utf8"),
  ]);

  assert.match(page, /type FilterLevel = "top-level" \| "derived"/);
  assert.match(page, /preset\.parent_mode \? `\$\{preset\.parent_mode\} › \$\{preset\.mode\}` : preset\.mode/);
  assert.match(page, /const describeFilterInspectionIssue = \(preset: DisclosureConditionPreset\)/);
  assert.match(page, /조건만 저장되어 있고 검색은 아직 실행하지 않았습니다/);
  assert.doesNotMatch(page, /FILTER_WORKFLOW_STATUS_LABELS/);
  assert.match(page, /presets\.filter\(\(preset\) => !preset\.parent_mode && preset\.status === "completed"\)/);
  assert.match(page, /완료된 상위 필터 선택/);
  assert.match(page, /\.\.\.\(filterParentMode \? \{ parent_mode: filterParentMode \} : \{\}\)/);
  assert.match(page, /deleteDisclosureConditionPreset\([\s\S]*?selectedPresetEntry\.mode,[\s\S]*?selectedPresetEntry\.parent_mode/);
  assert.match(page, /identityControls=\{/);
  assert.match(page, /libraryPresets=\{presets\}/);
  assert.match(page, /기본 필터는 02단계 전체를 검색하고 이후 HTML을 이 필터가 소유합니다/);
  assert.match(page, /파생 필터는 완료된 상위 필터 결과에만 조건을 추가하며, 한 단계까지만 만들 수 있습니다/);
  assert.doesNotMatch(page, /필터 구조/);
  assert.doesNotMatch(page, /필터 유형/);
  assert.doesNotMatch(page, /FILTER_MODE_KEYS/);
  assert.doesNotMatch(page, /html_parse_mode/);
  assert.doesNotMatch(page, /bond_issuance/);

  assert.match(client, /preset: Pick<DisclosureConditionPreset, "mode" \| "condition_blocks"> & \{ parent_mode\?: string \}/);
  assert.match(client, /\.\.\.\(parentMode \? \{ parent_mode: parentMode \} : \{\}\)/);

  assert.match(card, /id\?: string/);
  assert.match(card, /parent_mode\?: string/);
  assert.match(card, /getPresetIdentity\?:/);
  assert.match(card, /getPresetLabel\?:/);
  assert.match(card, /identityControls\?: ReactNode/);
  assert.match(card, /libraryPresets\?: DisclosureConditionPreset\[\]/);
  assert.match(card, /\{identityControls\}/);
  assert.match(card, /const mergePresets = libraryPresets \?\? presets/);
});

test("manual HTML workflows preserve derived filter identity", async () => {
  const [downloadPage, parsePage] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(htmlParsePagePath, "utf8"),
  ]);

  assert.match(downloadPage, /listDisclosureConditionPresets\(dataRoot\)/);
  assert.match(downloadPage, /preset\.parent_mode \? `\$\{preset\.parent_mode\} › \$\{preset\.mode\}` : preset\.mode/);
  assert.match(downloadPage, /mode: selectedFilterMode/);
  assert.match(downloadPage, /selectedFilterParentMode \? \{ parent_mode: selectedFilterParentMode \} : \{\}/);
  assert.match(downloadPage, /if \(selectedFilterParentMode\) \{[\s\S]*?상위 필터가 소유한 파일을 삭제할 수 없습니다/);
  assert.match(downloadPage, /파생 필터는 상위 필터의 HTML을 공유하므로 이 화면에서 파일을 삭제할 수 없습니다/);

  assert.match(parsePage, /presetIdentity\(preset\) === selectedPreset/);
  assert.match(parsePage, /const ownerMode = preset\.parent_mode \|\| preset\.mode/);
  assert.match(parsePage, /filter_mode: currentFilterMode/);
  assert.match(parsePage, /currentParentMode[\s\S]*?\{ filter_mode: currentFilterMode, parent_mode: currentParentMode \}/);
  assert.match(parsePage, /selectedPresetEntry\.parent_mode/);
  assert.match(parsePage, /getPresetIdentity=\{presetIdentity\}/);
  assert.match(parsePage, /getPresetLabel=\{presetLabel\}/);
});

test("automation keeps derived filters out until its profile stores parent identity", async () => {
  const page = await readFile(automationPagePath, "utf8");

  assert.match(page, /presets\.filter\(\(preset\) => !preset\.parent_mode\)/);
  assert.match(page, /공시 자동화에서는 기본 필터만 사용할 수 있습니다/);
});

test("derived disclosure filter documentation fixes ownership and depth", async () => {
  const paths = [
    "docs/disclosures/03-filter/features.md",
    "docs/disclosures/03-filter/reference.md",
    "docs/disclosures/04-external-html-download/features.md",
    "docs/disclosures/04-external-html-download/reference.md",
    "docs/disclosures/05-internal-html-download/features.md",
    "docs/disclosures/05-internal-html-download/reference.md",
  ];
  const docs = (await Promise.all(paths.map((path) => readFile(path, "utf8")))).join("\n");

  assert.match(docs, /03-filter\/<parent_mode>\/subfilters\/<mode>/);
  assert.match(docs, /한 단계/);
  assert.match(docs, /parent_result_fingerprint/);
  assert.match(docs, /상위 기본 필터가 소유한 외부 HTML/);
  assert.match(docs, /상위 기본 필터가 소유한 내부 HTML/);
  assert.match(docs, /fallback은 사용하지 않는다/);
});
