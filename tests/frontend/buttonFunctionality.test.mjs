import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const graphViewerExamplePath = "frontend/finiq_GUI/packages/graph-viewer/src/examples/GraphViewerExample.tsx";
const rightPanelPath = "frontend/finiq_GUI/packages/graph-viewer/src/components/RightPanel.tsx";
const ontologyNodeGraphPath = "frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyNodeGraph.tsx";
const companyGraphViewerPath = "frontend/finiq_GUI/apps/market-desk/src/app/company/[id]/CompanyGraphViewer.tsx";
const pathPickerPath = "frontend/finiq_GUI/packages/web-app/src/components/ui/PathPickerInput.tsx";
const graphViewerStylesPath = "frontend/finiq_GUI/apps/graph-viewer/src/globals.css";
const marketDeskStylesPath = "frontend/finiq_GUI/apps/market-desk/src/app/globals.css";
const graphViewerControllerPath = "frontend/finiq_GUI/packages/graph-viewer/src/core/useGraphViewer.ts";
const sharedButtonPath = "frontend/finiq_GUI/packages/ui/src/components/ui/button.tsx";
const sharedSelectPath = "frontend/finiq_GUI/packages/ui/src/components/ui/select.tsx";

test("shared selects do not lock page scroll when opened", async () => {
  const source = await readFile(sharedSelectPath, "utf8");

  assert.match(source, /modal = false/);
  assert.match(source, /<SelectPrimitive\.Root data-slot="select" modal=\{modal\} \{\.\.\.props\} \/>/);
});

test("shared buttons provide immediate press feedback", async () => {
  const source = await readFile(sharedButtonPath, "utf8");

  assert.match(source, /duration-\[120ms\]/);
  assert.match(source, /active:translate-y-px/);
  assert.match(source, /active:scale-\[0\.97\]/);
  assert.match(source, /active:opacity-80/);
  assert.match(source, /motion-reduce:active:transform-none/);
});

test("standalone graph selection actions are connected to graph state", async () => {
  const source = await readFile(graphViewerExamplePath, "utf8");

  assert.match(source, /const handleHideSelected = useCallback/);
  assert.match(source, /onContextAction\('node', nodeId, 'hide'\)/);
  assert.match(source, /onContextAction\('edge', edgeId, 'hide'\)/);
  assert.match(source, /viewer\.onBackgroundClick\(\)/);
  assert.match(source, /const handleApplyNeighborhood = useCallback/);
  assert.match(source, /onContextAction\('node', nodeId, 'neighbors'\)/);
  assert.match(source, /const handleJumpSelected = useCallback/);
  assert.match(source, /jumpToNodeId=\{jumpToNodeId\}/);
  assert.match(source, /onShowHidden=\{viewer\.showAll\}/);
  assert.doesNotMatch(source, /on(?:HideSelected|ShowHidden|ApplyNeighborhood|JumpSelected)=\{\(\) => \{\}\}/);
});

test("selection-only graph actions are disabled until a selection exists", async () => {
  const source = await readFile(rightPanelPath, "utf8");

  assert.match(source, /onClick=\{onJumpSelected\} disabled=\{!selectedNode\}/);
  assert.match(source, /onClick=\{onApplyNeighborhood\} disabled=\{!selectedNode\}/);
  assert.match(source, /onClick=\{onHideSelected\} disabled=\{selectedNodeIds\.size \+ selectedEdgeIds\.size === 0\}/);
});

test("hiding graph items removes them from selection state", async () => {
  const source = await readFile(graphViewerControllerPath, "utf8");

  assert.match(source, /setSelectedNodeIds\(\(prev\) => \{[\s\S]*?next\.delete\(id\)/);
  assert.match(source, /setSelectedEdgeIds\(\(prev\) => \{[\s\S]*?next\.delete\(id\)/);
});

test("selected-node icon actions stay inside the right panel and have names", async () => {
  const source = await readFile(rightPanelPath, "utf8");

  assert.match(source, /aria-label=\{selectedNode\.pinned \? 'Unpin Node' : 'Pin Node'\}/);
  assert.match(source, /aria-label="Delete Node"/);
  assert.equal(source.match(/className="h-7 flex-1"/g)?.length, 2);
});

test("MarketDesk graph preset actions use the graph viewer preset store", async () => {
  const [ontologySource, companySource] = await Promise.all([
    readFile(ontologyNodeGraphPath, "utf8"),
    readFile(companyGraphViewerPath, "utf8"),
  ]);

  for (const source of [ontologySource, companySource]) {
    assert.match(source, /stylePresets/);
    assert.match(source, /applyPreset/);
    assert.match(source, /savePreset/);
    assert.match(source, /presetNames=\{Object\.keys\(stylePresets\)\}/);
    assert.match(source, /onPresetChange=\{applyPreset\}/);
    assert.match(source, /onPresetSave=\{savePreset\}/);
    assert.doesNotMatch(source, /onPresetSave=\{\(\) => \{\}\}/);
  }
});

test("path picker icon button exposes its existing action title", async () => {
  const source = await readFile(pathPickerPath, "utf8");

  assert.match(source, /type="button"/);
  assert.match(source, /aria-label=\{title\}/);
  assert.match(source, /title=\{title\}/);
});

test("standalone graph viewer compiles utilities used by shared packages", async () => {
  const source = await readFile(graphViewerStylesPath, "utf8");

  assert.match(source, /@source "\.\.\/\.\.\/\.\.\/packages\/graph-viewer\/src\/\*\*\/\*\.tsx";/);
  assert.match(source, /@source "\.\.\/\.\.\/\.\.\/packages\/ui\/src\/\*\*\/\*\.tsx";/);
});

test("MarketDesk compiles utilities used by the shared graph viewer", async () => {
  const source = await readFile(marketDeskStylesPath, "utf8");

  assert.match(source, /@source "\.\.\/\.\.\/\.\.\/\.\.\/packages\/graph-viewer\/src\/\*\*\/\*\.tsx";/);
});
