import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const priceChartPath = "frontend/finiq_GUI/apps/market-desk/src/components/PriceChart.tsx";
const packagePath = "frontend/finiq_GUI/apps/market-desk/package.json";

test("price chart uses the open-source lightweight-charts package", async () => {
  const [source, packageJson] = await Promise.all([
    readFile(priceChartPath, "utf8"),
    readFile(packagePath, "utf8"),
  ]);
  const manifest = JSON.parse(packageJson);

  assert.equal(manifest.dependencies["lightweight-charts"], "^5.2.0");
  assert.match(source, /from "lightweight-charts"/);
  assert.match(source, /createChart/);
  assert.match(source, /CandlestickSeries/);
  assert.match(source, /HistogramSeries/);
  assert.match(source, /createSeriesMarkers/);
  assert.doesNotMatch(source, /@\/lib\/charts/);
});

test("price chart enables TradingView-style pan, zoom, and attribution", async () => {
  const source = await readFile(priceChartPath, "utf8");

  assert.match(source, /attributionLogo:\s*true/);
  assert.match(source, /handleScroll:\s*\{/);
  assert.match(source, /pressedMouseMove:\s*true/);
  assert.match(source, /horzTouchDrag:\s*true/);
  assert.match(source, /handleScale:\s*\{/);
  assert.match(source, /axisPressedMouseMove:\s*true/);
  assert.match(source, /mouseWheel:\s*true/);
  assert.match(source, /pinch:\s*true/);
});

test("price chart preserves the user viewport across resize and data refresh", async () => {
  const source = await readFile(priceChartPath, "utf8");
  const resizeObserverStart = source.indexOf("const resizeObserver = new ResizeObserver");
  const resizeObserverEnd = source.indexOf("resizeObserver.observe", resizeObserverStart);
  const resizeObserverBlock = source.slice(resizeObserverStart, resizeObserverEnd);

  assert.match(source, /getVisibleLogicalRange\(\)/);
  assert.match(source, /setVisibleLogicalRange\(visibleRange\)/);
  assert.match(source, /hasUserViewportRef/);
  assert.doesNotMatch(resizeObserverBlock, /timeScale\(\)\.fitContent\(\)/);
});
