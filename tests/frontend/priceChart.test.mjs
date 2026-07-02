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
  assert.match(source, /\{subtitle \? <p className="text-sm text-slate-500 dark:text-slate-400">\{subtitle\}<\/p> : null\}/);
});

test("price chart can render close-only line mode", async () => {
  const [source, chartSource] = await Promise.all([
    readFile(priceChartPath, "utf8"),
    readFile(chartLibPath, "utf8"),
  ]);

  assert.match(source, /chartType\?: "candlestick" \| "line"/);
  assert.match(source, /chartType = "candlestick"/);
  assert.match(source, /LineSeries/);
  assert.match(source, /value: d\.close/);
  assert.match(chartSource, /export const LineSeries = "LineSeries" as const/);
  assert.match(chartSource, /drawLineSeries/);
});

test("price chart keeps price and volume on separate vertical axes", async () => {
  const [source, chartSource] = await Promise.all([
    readFile(priceChartPath, "utf8"),
    readFile(chartLibPath, "utf8"),
  ]);

  const priceScaleIndex = source.indexOf("priceSeries.priceScale().applyOptions");
  const volumeScaleIndex = source.indexOf("volumeSeries.priceScale().applyOptions");
  assert.notEqual(priceScaleIndex, -1);
  assert.notEqual(volumeScaleIndex, -1);

  const priceScaleBlock = source.slice(priceScaleIndex, volumeScaleIndex);
  const volumeScaleBlock = source.slice(volumeScaleIndex, source.indexOf("chart.subscribeCrosshairMove", volumeScaleIndex));
  assert.match(priceScaleBlock, /bottom:\s*0\.28/);
  assert.match(volumeScaleBlock, /top:\s*0\.76/);
  assert.match(chartSource, /drawVolumeAxis/);
  assert.match(chartSource, /getVolumeRange/);
  assert.match(chartSource, /DEFAULT_LEFT_SCALE_WIDTH/);
  assert.match(chartSource, /leftScaleWidth/);
  assert.match(chartSource, /ctx\.rect\(layout\.plotLeft, priceRect\.top/);
  assert.match(chartSource, /ctx\.clip\(\)/);
});

test("price chart shows TradingView-style hover OHLCV readout", async () => {
  const source = await readFile(priceChartPath, "utf8");

  assert.match(source, /useState/);
  assert.match(source, /activeCandle/);
  assert.match(source, /formatSignedChange/);
  assert.match(source, /formatPercentChange/);
  assert.match(source, /formatVolume/);
  assert.match(source, /previousClose/);
  assert.match(source, /setActiveCandle\(null\)/);
  assert.match(source, /setActiveCandle\(hoverCandle\)/);
  assert.match(source, /useEffect\(\(\) => \{\s*setActiveCandle\(null\);\s*\}, \[data\]\);/);
  assert.match(source, />O\s*\{/);
  assert.match(source, />H\s*\{/);
  assert.match(source, />L\s*\{/);
  assert.match(source, />C\s*\{/);
  assert.match(source, />Vol\s*\{/);
});

test("FINIQ chart draws dashed crosshair with price and time labels", async () => {
  const source = await readFile(chartLibPath, "utf8");

  assert.match(source, /drawCrosshair/);
  assert.match(source, /ctx\.setLineDash\(\[4, 4\]\)/);
  assert.match(source, /this\.yToPrice\(y, priceRange, priceRect\)/);
  assert.match(source, /priceText/);
  assert.match(source, /timeText/);
  assert.match(source, /layout\.timeScaleTop/);
});

test("FINIQ chart pans price vertically while keeping volume on the shared time range", async () => {
  const source = await readFile(chartLibPath, "utf8");

  assert.match(source, /startClientY:\s*event\.clientY/);
  assert.match(source, /startPriceRange/);
  assert.match(source, /panPriceRangeByPixels/);
  assert.match(source, /this\.manualPriceRange\s*=/);
  assert.match(source, /const visibleRange = this\.getVisibleRange\(data\.length\)/);
  assert.match(source, /const x = this\.getX\(index, data\.length, layout\)/);
});

test("FINIQ chart allows manual volume-axis scaling from the left axis", async () => {
  const source = await readFile(chartLibPath, "utf8");

  assert.match(source, /manualVolumeRange/);
  assert.match(source, /volumeScaleDragState/);
  assert.match(source, /x <= layout\.plotLeft && x >= layout\.plotLeft - layout\.leftScaleWidth/);
  assert.match(source, /zoomVolumeRangeAtY/);
  assert.match(source, /this\.manualVolumeRange\s*=/);
});

test("FINIQ chart does not auto-pad non-negative prices below zero", async () => {
  const source = await readFile(chartLibPath, "utf8");

  assert.match(source, /min >= 0 \? Math\.max\(0, min - padding\) : min - padding/);
});

test("price chart supports configurable disclosure marker placement and shape", async () => {
  const [source, chartSource] = await Promise.all([
    readFile(priceChartPath, "utf8"),
    readFile(chartLibPath, "utf8"),
  ]);

  assert.match(source, /markerStyleDefault\?: MarkerStyleConfig/);
  assert.match(source, /markerStylesByGroup\?: Record<string, MarkerStyleConfig>/);
  assert.match(source, /resolveMarkerStyle/);
  assert.match(source, /const groupStyle = marker\.group \? markerStylesByGroup\[marker\.group\] : undefined/);
  assert.match(source, /size: groupStyle\?\.size \?\? markerStyleDefault\.size/);
  assert.match(source, /lineWidth: groupStyle\?\.lineWidth \?\? markerStyleDefault\.lineWidth/);
  assert.match(chartSource, /marker\.position === "paneTop"/);
  assert.match(chartSource, /marker\.position === "paneBottom"/);
  assert.match(chartSource, /marker\.shape === "arrowDown"/);
  assert.match(chartSource, /const markerSize = clamp\(toNumber\(marker\.size, 4\), 2, 14\)/);
  assert.match(chartSource, /ctx\.lineWidth = clamp\(toNumber\(marker\.lineWidth, 1\), 1, 6\)/);
});

test("FINIQ chart renders all disclosure markers on the same date", async () => {
  const source = await readFile(chartLibPath, "utf8");

  assert.match(source, /markersByTime/);
  assert.match(source, /forEach\(\(marker\) =>/);
  assert.doesNotMatch(source, /new Map\(markers\.map\(\(marker\) => \[marker\.time, marker\]\)\)/);
});
