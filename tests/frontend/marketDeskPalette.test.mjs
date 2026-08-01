import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const globalsPath = path.resolve("frontend/finiq_GUI/apps/market-desk/src/app/globals.css");
const topbarPath = path.resolve("frontend/finiq_GUI/packages/web-app/src/components/layout/Topbar.tsx");
const sidebarPath = path.resolve("frontend/finiq_GUI/packages/web-app/src/components/layout/WorkflowSidebar.tsx");
const tabsPath = path.resolve("frontend/finiq_GUI/packages/web-app/src/components/layout/WorkflowTabs.tsx");

test("MarketDesk primary accent uses monochrome TradingView-style tokens", async () => {
  const source = await readFile(globalsPath, "utf8");

  assert.match(source, /--color-primary-foreground: var\(--tv-accent-foreground\)/);
  assert.match(source, /--tv-accent: #131722/);
  assert.match(source, /--tv-accent-foreground: #ffffff/);
  assert.match(source, /--tv-accent-soft: rgb\(19 23 34 \/ 0\.08\)/);
  assert.match(source, /--tv-accent: #f0f3fa/);
  assert.match(source, /--tv-accent-foreground: #131722/);
  assert.match(source, /--tv-accent-soft: rgb\(240 243 250 \/ 0\.14\)/);
  assert.doesNotMatch(source, /--tv-accent:\s*#2962ff/i);
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
  assert.match(source, /aria-current=\{activeItem\?\.href === item\.href \? "page" : undefined\}/);
  assert.match(source, /focus-visible:ring-2/);
});
