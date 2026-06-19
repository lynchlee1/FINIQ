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

test("FINIQ chart applies configurable zoom sensitivity", async () => {
  const [source, priceChartSource] = await Promise.all([
    readFile(chartLibPath, "utf8"),
    readFile(priceChartPath, "utf8"),
  ]);

  assert.match(priceChartSource, /zoomSensitivity\?: number/);
  assert.match(priceChartSource, /zoomSensitivity = 0\.55/);
  assert.match(priceChartSource, /interaction:\s*\{\s*zoomSensitivity/);
  assert.match(source, /getZoomSensitivity/);
  assert.match(source, /wheelZoomFactor/);
  assert.match(source, /clamp\(toNumber\(this\.options\.interaction\?\.zoomSensitivity, 0\.55\), 0\.2, 1\.5\)/);
});

test("price chart preserves the user viewport across resize and data refresh", async () => {
  const source = await readFile(priceChartPath, "utf8");
  const resizeObserverStart = source.indexOf("const resizeObserver = new ResizeObserver");
  const resizeObserverEnd = source.indexOf("resizeObserver.observe", resizeObserverStart);
  const resizeObserverBlock = source.slice(resizeObserverStart, resizeObserverEnd);

  assert.match(source, /hasFittedContentRef/);
  assert.doesNotMatch(resizeObserverBlock, /timeScale\(\)\.fitContent\(\)/);
});

test("price chart can hide its internal title block", async () => {
  const source = await readFile(priceChartPath, "utf8");

  assert.match(source, /showHeader\?: boolean/);
  assert.match(source, /showHeader = true/);
  assert.match(source, /\{showHeader \? \(/);
});
