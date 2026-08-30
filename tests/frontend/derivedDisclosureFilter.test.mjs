import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const filterPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx";
const presetClientPath = "frontend/finiq_GUI/apps/market-desk/src/lib/disclosureConditionPresets.ts";
const conditionCardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/DisclosureConditionFilterCard.tsx";
const downloadPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/external-html-download/_components/DisclosureHtmlDownloadPageView.tsx";
const sectionSplitPagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
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
  assert.match(page, /const filterPagePresetLabel = \(preset: DisclosureConditionPreset\) => preset\.mode/);
  assert.match(page, /getPresetLabel=\{filterPagePresetLabel\}/);
  assert.match(page, /getLibraryPresetLabel=\{presetLabel\}/);
  assert.match(page, /presetSelectorLabel=\{filterLevel === "derived" \? "파생 필터" : "조건검색 필터"\}/);
  assert.match(page, /presetSelectorHelpDescription=\{filterLevel === "derived"/);
  assert.match(page, /const describeFilterInspectionIssue = \(preset: DisclosureConditionPreset\)/);
  assert.match(page, /조건만 저장되어 있고 검색은 아직 실행하지 않았습니다/);
  assert.doesNotMatch(page, /FILTER_WORKFLOW_STATUS_LABELS/);
  assert.match(page, /presets\.filter\(\(preset\) => !preset\.parent_mode && preset\.status === "completed"\)/);
  assert.match(page, /preset\.parent_mode && parentMode && preset\.parent_mode === parentMode/);
  assert.doesNotMatch(page, /!parentMode \|\| preset\.parent_mode === parentMode/);
  assert.match(page, /완료된 상위 필터 선택/);
  assert.match(page, /\.\.\.\(filterParentMode \? \{ parent_mode: filterParentMode \} : \{\}\)/);
  assert.match(page, /deleteDisclosureConditionPreset\([\s\S]*?selectedPresetEntry\.mode,[\s\S]*?selectedPresetEntry\.parent_mode/);
  assert.match(page, /identityControls=\{/);
  assert.match(page, /libraryPresets=\{presets\}/);
  assert.doesNotMatch(page, /기본 필터는 02단계 전체를 검색하고 이후 HTML을 이 필터가 소유합니다/);
  assert.match(page, /최종 결과는 상위 필터를 벗어나지 않습니다/);
  assert.match(page, /OR 조건을 추가하면 파생 조건식 자체가 예상보다 넓어질 수 있으니/);
  assert.doesNotMatch(page, /필터 구조/);
  assert.doesNotMatch(page, /필터 유형/);
  assert.doesNotMatch(page, /FILTER_MODE_KEYS/);
  assert.doesNotMatch(page, /html_parse_mode/);
  assert.doesNotMatch(page, /bond_issuance/);

  assert.match(client, /if \(!options\.force && cached\?\.promise\) return cached\.promise/);
  assert.match(client, /preset: Pick<DisclosureConditionPreset, "mode" \| "condition_blocks"> & \{ parent_mode\?: string \}/);
  assert.match(client, /\.\.\.\(parentMode \? \{ parent_mode: parentMode \} : \{\}\)/);

  assert.match(card, /id\?: string/);
  assert.match(card, /parent_mode\?: string/);
  assert.match(card, /getPresetIdentity\?:/);
  assert.match(card, /getPresetLabel\?:/);
  assert.match(card, /getLibraryPresetLabel\?:/);
  assert.match(card, /identityControls\?: ReactNode/);
  assert.match(card, /presetSelectorHelpDescription\?: string/);
  assert.match(card, /libraryPresets\?: DisclosureConditionPreset\[\]/);
  assert.match(card, /presetSelectorLabel\?: string/);
  assert.match(card, /showPresetActions\?: boolean/);
  assert.match(card, /allowCreate=\{showPresetActions\}/);
  assert.match(card, /<FieldHelpPopover \/>/);
  assert.match(card, /ariaLabel="파생 필터 주의사항" title="파생 필터 주의사항"/);
  assert.match(card, /icon="info"/);
  assert.match(card, /presetSelectorHelpDescription \? <DerivedFilterHelpPopover description=\{presetSelectorHelpDescription\} \/>/);
  assert.match(card, /className="flex h-5 items-center gap-1\.5"/);
  assert.match(card, /className="inline-flex h-5 items-center leading-none dark:text-slate-300"/);
  assert.match(card, /<div className="relative flex h-5 items-center">/);
  assert.match(card, /className="inline-flex h-5 w-5 shrink-0 items-center justify-center/);
  assert.match(card, /<CardContent className="space-y-4">/);
  assert.doesNotMatch(card, /className="h-9/);
  assert.match(card, /const mergePresets = libraryPresets \?\? presets/);
  assert.match(card, /getPresetLabel=\{getLibraryPresetLabel \?\? getPresetLabel\}/);
});

test("HTML storage workflows hide derived filters while parsing preserves their identity", async () => {
  const [downloadPage, sectionSplitPage, parsePage] = await Promise.all([
    readFile(downloadPagePath, "utf8"),
    readFile(sectionSplitPagePath, "utf8"),
    readFile(htmlParsePagePath, "utf8"),
  ]);

  assert.match(downloadPage, /listDisclosureConditionPresets\(dataRoot\)/);
  assert.match(downloadPage, /setFilterPresets\(response\.presets\.filter\(\(preset\) => !preset\.parent_mode\)\)/);
  assert.match(sectionSplitPage, /setFilterPresets\(response\.presets\.filter\(\(preset\) => !preset\.parent_mode\)\)/);
  assert.match(downloadPage, /preset\.parent_mode \? `\$\{preset\.parent_mode\} › \$\{preset\.mode\}` : preset\.mode/);
  assert.match(downloadPage, /mode: selectedFilterMode/);
  assert.match(downloadPage, /const selectedFilterMode = selectedFilterPreset\?\.mode \|\| ""/);
  assert.match(downloadPage, /<FilterPresetCombobox/);
  assert.match(downloadPage, /getPresetIdentity=\{presetIdentity\}/);
  assert.match(downloadPage, /getPresetLabel=\{presetLabel\}/);
  assert.match(downloadPage, /allowCreate=\{false\}/);
  assert.doesNotMatch(downloadPage, /selectedFilterId \|\| htmlParseMode/);
  assert.match(downloadPage, /selectedFilterParentMode \? \{ parent_mode: selectedFilterParentMode \} : \{\}/);
  assert.match(downloadPage, /if \(!selectedFilterPreset\) \{[\s\S]*?조건검색 필터를 선택하세요/);
  assert.match(downloadPage, /if \(selectedFilterParentMode\) \{[\s\S]*?상위 필터가 소유한 파일을 삭제할 수 없습니다/);
  assert.match(downloadPage, /파생 필터는 상위 필터의 HTML을 공유하므로 이 화면에서 파일을 삭제할 수 없습니다/);
  assert.doesNotMatch(downloadPage, /상위 필터 .*HTML에서 파생 필터 .* 대상만 사용합니다/);

  assert.match(parsePage, /presetIdentity\(preset\) === selectedPreset/);
  assert.match(parsePage, /mode: currentFilterMode/);
  assert.match(parsePage, /parser_method: parserMethod/);
  assert.match(parsePage, /currentParentMode[\s\S]*?\{ parent_mode: currentParentMode \}/);
  assert.doesNotMatch(parsePage, /filter_mode:/);
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
    "docs/disclosures/03-filter/storage.md",
    "docs/disclosures/03-filter/execution.md",
    "docs/disclosures/04-external-html/download.md",
    "docs/disclosures/04-external-html/storage.md",
    "docs/disclosures/05-internal-html/download.md",
  ];
  const docs = (await Promise.all(paths.map((path) => readFile(path, "utf8")))).join("\n");

  assert.match(docs, /03-filter\/<parent_mode>\/subfilters\/<mode>/);
  assert.match(docs, /한 단계/);
  assert.match(docs, /parent_result_fingerprint/);
  assert.match(docs, /상위 기본 필터의 외부 HTML/);
  assert.match(docs, /상위 기본 필터의 내부 HTML/);
  assert.match(docs, /상위 결과 오류를 02단계 전체 검색이나 다른 필터 결과로 보완하지 않는다/);
});
