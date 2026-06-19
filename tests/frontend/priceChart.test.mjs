import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const priceChartPath = "frontend/finiq_GUI/apps/market-desk/src/components/PriceChart.tsx";
const chartLibPath = "frontend/finiq_GUI/apps/market-desk/src/lib/charts.ts";
const packagePath = "frontend/finiq_GUI/apps/market-desk/package.json";

test("price chart uses FINIQ-owned chart code without external logo obligations", async () => {
  const [source, packageJson] = await Promise.all([
    readFile(priceChartPath, "utf8"),
    readFile(packagePath, "utf8"),
  ]);
  const manifest = JSON.parse(packageJson);

  assert.equal(manifest.dependencies["lightweight-charts"], undefined);
  assert.match(source, /from "@\/lib\/charts"/);
  assert.match(source, /createChart/);
  assert.match(source, /CandlestickSeries/);
  assert.match(source, /HistogramSeries/);
  assert.match(source, /createSeriesMarkers/);
  assert.doesNotMatch(source, /from "lightweight-charts"/);
  assert.doesNotMatch(source, /TradingView/);
  assert.doesNotMatch(source, /attributionLogo/);
});

test("FINIQ chart supports free pan, zoom, and price-axis scaling", async () => {
  const source = await readFile(chartLibPath, "utf8");

  assert.match(source, /onPointerDown/);
  assert.match(source, /onWindowPointerMove/);
  assert.match(source, /onWheel/);
  assert.match(source, /priceScaleDragState/);
  assert.match(source, /manualPriceRange/);
  assert.match(source, /onDoubleClick/);
  assert.doesNotMatch(source, /TradingView/);
});

test("price chart preserves the user viewport across resize and data refresh", async () => {
  const source = await readFile(priceChartPath, "utf8");
  const resizeObserverStart = source.indexOf("const resizeObserver = new ResizeObserver");
  const resizeObserverEnd = source.indexOf("resizeObserver.observe", resizeObserverStart);
  const resizeObserverBlock = source.slice(resizeObserverStart, resizeObserverEnd);

  assert.match(source, /hasFittedContentRef/);
  assert.doesNotMatch(resizeObserverBlock, /timeScale\(\)\.fitContent\(\)/);
});
