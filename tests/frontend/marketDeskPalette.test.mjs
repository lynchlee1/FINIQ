import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const globalsPath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/app/globals.css");
const layoutPath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/app/layout.tsx");
const topbarPath = path.resolve("frontend/finiq_GUI/packages/web-app/src/components/layout/Topbar.tsx");
const sidebarPath = path.resolve("frontend/finiq_GUI/packages/web-app/src/components/layout/WorkflowSidebar.tsx");
const tabsPath = path.resolve("frontend/finiq_GUI/packages/web-app/src/components/layout/WorkflowTabs.tsx");
const cardPath = path.resolve("frontend/finiq_GUI/packages/ui/src/components/ui/card.tsx");
const buttonPath = path.resolve("frontend/finiq_GUI/packages/ui/src/components/ui/button.tsx");
const inputPath = path.resolve("frontend/finiq_GUI/packages/ui/src/components/ui/input.tsx");

test("MarketDesk restores the flat slate palette and typography", async () => {
  const source = await readFile(globalsPath, "utf8");
  const layoutSource = await readFile(layoutPath, "utf8");

  assert.match(source, /--color-primary-foreground: var\(--tv-accent-foreground\)/);
  assert.match(source, /--tv-bg: #f8fafc/);
  assert.match(source, /--tv-border: #e2e8f0/);
  assert.match(source, /--tv-accent: #0f172a/);
  assert.match(source, /--tv-accent-foreground: #ffffff/);
  assert.match(source, /--tv-bg: #0d1117/);
  assert.match(source, /--tv-border: #30363d/);
  assert.match(source, /--tv-accent: #2f81f7/);
  assert.match(source, /--tv-shadow: none/);
  assert.match(source, /--font-sans: var\(--font-ibm-plex-sans-kr\)/);
  assert.match(source, /--font-mono: var\(--font-space-grotesk\)/);
  assert.match(layoutSource, /IBM_Plex_Sans_KR/);
  assert.match(layoutSource, /Space_Grotesk/);
});

test("shared navigation active states use accent foreground instead of fixed white", async () => {
  const sources = await Promise.all([
    readFile(topbarPath, "utf8"),
    readFile(sidebarPath, "utf8"),
    readFile(tabsPath, "utf8"),
  ]);

  for (const source of sources) {
    assert.match(source, /text-\[var\(--tv-accent-foreground\)\]/);
    assert.doesNotMatch(source, /bg-\[var\(--tv-accent\)\] text-white/);
  }
});

test("top navigation presents compact segmented selection semantics", async () => {
  const source = await readFile(topbarPath, "utf8");

  assert.match(source, /bg-\[var\(--tv-surface-muted\)\] p-1/);
  assert.match(source, /whitespace-nowrap rounded-lg/);
  assert.match(source, /aria-current=\{activeItem\?\.href === item\.href \? "page" : undefined\}/);
  assert.match(source, /focus-visible:ring-2/);
});

test("structural surfaces stay flat while semantic selection buttons keep the larger radius", async () => {
  const [cardSource, buttonSource, topbarSource, sidebarSource, tabsSource, inputSource] = await Promise.all([
    readFile(cardPath, "utf8"),
    readFile(buttonPath, "utf8"),
    readFile(topbarPath, "utf8"),
    readFile(sidebarPath, "utf8"),
    readFile(tabsPath, "utf8"),
    readFile(inputPath, "utf8"),
  ]);

  assert.match(cardSource, /rounded-lg border border-border/);
  assert.doesNotMatch(cardSource, /shadow-(?:sm|md|lg|xl|2xl)/);
  assert.match(inputSource, /rounded-md border border-input bg-transparent/);
  assert.match(buttonSource, /rounded-md/);
  assert.match(buttonSource, /\[&\[aria-pressed\]\]:rounded-lg/);
  assert.match(topbarSource, /whitespace-nowrap rounded-lg/);
  assert.match(sidebarSource, /flex items-center rounded-lg/);
  assert.match(tabsSource, /justify-center gap-3 rounded-lg/);

  for (const source of [topbarSource, sidebarSource, tabsSource]) {
    assert.doesNotMatch(source, /backdrop-blur/);
    assert.doesNotMatch(source, /shadow-\[var\(--tv-shadow\)\]/);
  }
});
