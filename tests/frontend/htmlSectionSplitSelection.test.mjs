import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = "frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx";
const cardPath = "frontend/finiq_GUI/apps/market-desk/src/components/disclosures/HtmlSectionPatternCard.tsx";

test("HTML section save requires an explicit decision for every TOC pattern", async () => {
  const [pageSource, cardSource] = await Promise.all([
    readFile(pagePath, "utf8"),
    readFile(cardPath, "utf8"),
  ]);

  assert.doesNotMatch(pageSource, /defaultPatternTocIds/);
  assert.match(pageSource, /const selected = current\[signature\] \|\| \[\]/);
  assert.match(pageSource, /const undecidedPatterns = sectionPatterns\.filter/);
  assert.match(pageSource, /모든 목차 구성을 직접 결정하세요/);
  assert.match(cardSource, /selectedPatternTocIds\[pattern\.signature\] \?\? \[\]/);
  assert.doesNotMatch(cardSource, /defaultSelectAll/);
});
