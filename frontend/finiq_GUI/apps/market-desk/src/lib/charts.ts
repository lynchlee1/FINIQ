"use client"

const DEFAULT_LEFT_SCALE_WIDTH = 88;
const DEFAULT_RIGHT_SCALE_WIDTH = 72;
const DEFAULT_TIME_SCALE_HEIGHT = 28;
const DEFAULT_PADDING = 12;
const DEFAULT_GRID_LINES = 5;
const DEFAULT_TIME_TICKS = 6;

export const BarSeries = "BarSeries" as const;
export const CandlestickSeries = "CandlestickSeries" as const;
export const HistogramSeries = "HistogramSeries" as const;
export const LineSeries = "LineSeries" as const;

export type SeriesType = typeof BarSeries | typeof CandlestickSeries | typeof HistogramSeries | typeof LineSeries;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function toNumber(value: any, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function alphaColor(color: string, alphaHex: string) {
  if (typeof color !== "string") {
    return "#94a3b866";
  }
  if (color.startsWith("#") && color.length === 7) {
    return `${color}${alphaHex}`;
  }
  return color;
}

class PriceScaleApi {
  series: SeriesApi;
  constructor(series: SeriesApi) {
    this.series = series;
  }

  applyOptions(options: any = {}) {
    const nextMargins = options.scaleMargins || {};
    this.series.scaleMargins = {
      ...this.series.scaleMargins,
      ...nextMargins,
    };
    this.series.chart.render();
  }
}

class SeriesApi {
  chart: ChartApi;
  type: SeriesType;
  options: any;
  data: any[] = [];
  markers: any[] = [];
  scaleMargins = { top: 0.1, bottom: 0.1 };
  priceScaleApi: PriceScaleApi;

  constructor(chart: ChartApi, type: SeriesType, options: any = {}) {
    this.chart = chart;
    this.type = type;
    this.options = { ...options };
    this.priceScaleApi = new PriceScaleApi(this);
  }

  setData(data: any[]) {
    this.data = Array.isArray(data) ? [...data] : [];
    this.chart.render();
  }

  priceScale() {
    return this.priceScaleApi;
  }

  applyOptions(options: any = {}) {
    this.options = {
      ...this.options,
      ...options,
    };
    this.chart.render();
  }
}

class MarkerHandle {
  series: SeriesApi;
  constructor(series: SeriesApi, markers: any[]) {
    this.series = series;
    this.setMarkers(markers);
  }

  setMarkers(markers: any[]) {
    this.series.markers = Array.isArray(markers) ? [...markers] : [];
    this.series.chart.render();
  }
}

class TimeScaleApi {
  chart: ChartApi;
  constructor(chart: ChartApi) {
    this.chart = chart;
  }

  fitContent() {
    this.chart.fitContent();
  }
}

export class ChartApi {
  container: HTMLElement;
  options: any;
  series: SeriesApi[] = [];
  crosshairCallbacks: ((param: any) => void)[] = [];
  crosshair: any = null;
  visibleRange: { from: number; to: number } | null = null;
  manualPriceRange: { min: number; max: number } | null = null;
  dragState: any = null;
  priceScaleDragState: any = null;
  timeScaleApi: TimeScaleApi;
  devicePixelRatio: number;
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  width: number = 0;
  height: number = 0;

  constructor(container: HTMLElement, options: any = {}) {
    this.container = container;
    this.options = { ...options };
    this.timeScaleApi = new TimeScaleApi(this);
    this.devicePixelRatio = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;

    this.canvas = document.createElement("canvas");
    this.canvas.style.position = "absolute";
    this.canvas.style.inset = "0";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.display = "block";

    this.container.innerHTML = "";
    this.container.style.position = "relative";
    this.container.appendChild(this.canvas);
    const context = this.canvas.getContext("2d");
    if (!context) throw new Error("Could not get 2D context");
    this.ctx = context;
    this.canvas.style.cursor = "crosshair";

    this.canvas.addEventListener("mousedown", (event) => this.onPointerDown(event));
    this.canvas.addEventListener("mousemove", (event) => this.onPointerMove(event));
    this.canvas.addEventListener("mouseleave", () => this.onPointerLeave());
    this.canvas.addEventListener("dblclick", (event) => this.onDoubleClick(event));
    this.canvas.addEventListener("wheel", (event) => this.onWheel(event), { passive: false });
    
    if (typeof window !== 'undefined') {
      this._onWindowMouseUp = () => this.onPointerUp();
      this._onWindowMouseMove = (event: MouseEvent) => this.onWindowPointerMove(event);
      window.addEventListener("mouseup", this._onWindowMouseUp);
      window.addEventListener("mousemove", this._onWindowMouseMove);
    }

    this.resize(toNumber(options.width, this.container.clientWidth), toNumber(options.height, this.container.clientHeight));
  }

  private _onWindowMouseUp: (() => void) | null = null;
  private _onWindowMouseMove: ((event: MouseEvent) => void) | null = null;

  destroy() {
    if (typeof window !== 'undefined') {
      if (this._onWindowMouseUp) window.removeEventListener("mouseup", this._onWindowMouseUp);
      if (this._onWindowMouseMove) window.removeEventListener("mousemove", this._onWindowMouseMove);
    }
    this.container.innerHTML = "";
    this.series = [];
    this.crosshairCallbacks = [];
  }

  addSeries(type: SeriesType, options: any = {}) {
    const series = new SeriesApi(this, type, options);
    this.series.push(series);
    this.render();
    return series;
  }

  applyOptions(options: any = {}) {
    this.options = {
      ...this.options,
      ...options,
    };
    this.resize(
      toNumber(options.width, this.container.clientWidth),
      toNumber(options.height, this.container.clientHeight),
    );
  }

  timeScale() {
    return this.timeScaleApi;
  }

  subscribeCrosshairMove(callback: (param: any) => void) {
    if (typeof callback === "function") {
      this.crosshairCallbacks.push(callback);
    }
  }

  fitContent() {
    this.manualPriceRange = null;
    const count = this.getPriceSeries()?.data?.length || 0;
    if (count <= 1) {
      this.visibleRange = { from: 0, to: 0 };
    } else {
      this.visibleRange = { from: 0, to: count - 1 };
    }
    this.render();
  }

  resize(width: number, height: number) {
    const cssWidth = Math.max(1, Math.round(width || this.container.clientWidth || 1));
    const cssHeight = Math.max(1, Math.round(height || this.container.clientHeight || 1));
    this.width = cssWidth;
    this.height = cssHeight;
    this.canvas.width = Math.round(cssWidth * this.devicePixelRatio);
    this.canvas.height = Math.round(cssHeight * this.devicePixelRatio);
    this.ctx.setTransform(this.devicePixelRatio, 0, 0, this.devicePixelRatio, 0, 0);
    this.render();
  }

  onPointerMove(event: MouseEvent) {
    const priceSeries = this.getPriceSeries();
    if (!priceSeries || !priceSeries.data.length) {
      return;
    }
    if (this.dragState || this.priceScaleDragState) {
      return;
    }
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const layout = this.getLayout();
    if (x >= layout.rightScaleLeft && y >= layout.plotTop && y <= layout.plotBottom) {
      this.canvas.style.cursor = "ns-resize";
      return;
    }
    this.canvas.style.cursor = "crosshair";
    if (x < layout.plotLeft || x > layout.plotRight || y < layout.plotTop || y > layout.plotBottom) {
      return;
    }
    const index = this.getNearestIndex(x, priceSeries.data.length, layout);
    this.crosshair = { index, x, y };
    this.emitCrosshair(index);
    this.render();
  }

  onPointerDown(event: MouseEvent) {
    if (event.button !== 0) {
      return;
    }
    const priceSeries = this.getPriceSeries();
    if (!priceSeries || priceSeries.data.length <= 1) {
      return;
    }
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const layout = this.getLayout();
    if (x >= layout.rightScaleLeft && y >= layout.plotTop && y <= layout.plotBottom) {
      this.priceScaleDragState = {
        startClientY: event.clientY,
        startRange: { ...this.getPriceRange() },
      };
      this.canvas.style.cursor = "ns-resize";
      event.preventDefault();
      return;
    }
    if (x < layout.plotLeft || x > layout.plotRight || y < layout.plotTop || y > layout.plotBottom) {
      return;
    }
    const range = this.getVisibleRange(priceSeries.data.length);
    this.dragState = {
      startClientX: event.clientX,
      startRange: { ...range },
    };
    this.canvas.style.cursor = "grabbing";
    event.preventDefault();
  }

  onWindowPointerMove(event: MouseEvent) {
    if (this.priceScaleDragState) {
      const startRange = this.priceScaleDragState.startRange;
      const center = (startRange.min + startRange.max) / 2;
      const startSpan = Math.max(startRange.max - startRange.min, 1e-9);
      const deltaY = event.clientY - this.priceScaleDragState.startClientY;
      const nextSpan = startSpan * Math.exp(deltaY / 180);
      this.manualPriceRange = {
        min: center - nextSpan / 2,
        max: center + nextSpan / 2,
      };
      this.crosshair = null;
      this.emitCrosshair(null);
      this.render();
      return;
    }
    if (!this.dragState) {
      return;
    }
    const priceSeries = this.getPriceSeries();
    if (!priceSeries || priceSeries.data.length <= 1) {
      return;
    }
    const layout = this.getLayout();
    const span = Math.max(this.dragState.startRange.to - this.dragState.startRange.from, 1);
    const pixelsPerIndex = (layout.plotRight - layout.plotLeft) / span;
    const deltaX = event.clientX - this.dragState.startClientX;
    const shift = deltaX / Math.max(pixelsPerIndex, 1e-6);
    const nextRange = this.clampVisibleRange(
      this.dragState.startRange.from - shift,
      this.dragState.startRange.to - shift,
      priceSeries.data.length,
    );
    this.visibleRange = nextRange;
    this.crosshair = null;
    this.emitCrosshair(null);
    this.render();
  }

  onPointerUp() {
    if (!this.dragState && !this.priceScaleDragState) {
      return;
    }
    this.dragState = null;
    this.priceScaleDragState = null;
    this.canvas.style.cursor = "crosshair";
  }

  onWheel(event: WheelEvent) {
    const priceSeries = this.getPriceSeries();
    if (!priceSeries || priceSeries.data.length <= 1) {
      return;
    }
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const layout = this.getLayout();
    const wheelZoomFactor = this.getWheelZoomFactor(event.deltaY);
    if (x >= layout.rightScaleLeft && y >= layout.plotTop && y <= layout.plotBottom) {
      event.preventDefault();
      this.zoomPriceRangeAtY(y, wheelZoomFactor, layout);
      return;
    }
    if (x < layout.plotLeft || x > layout.plotRight || y < layout.plotTop || y > layout.plotBottom) {
      return;
    }
    event.preventDefault();
    const currentRange = this.getVisibleRange(priceSeries.data.length);
    const span = Math.max(currentRange.to - currentRange.from, 1);
    const ratio = (x - layout.plotLeft) / Math.max(layout.plotRight - layout.plotLeft, 1);
    const anchor = currentRange.from + span * ratio;
    const minSpan = Math.min(Math.max(6, priceSeries.data.length * 0.04), priceSeries.data.length - 1 || 1);
    const maxSpan = Math.max(priceSeries.data.length - 1, 1);
    const nextSpan = clamp(span * wheelZoomFactor, minSpan, maxSpan);
    const nextFrom = anchor - nextSpan * ratio;
    const nextTo = nextFrom + nextSpan;
    this.visibleRange = this.clampVisibleRange(nextFrom, nextTo, priceSeries.data.length);
    this.render();
  }

  onDoubleClick(event: MouseEvent) {
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const layout = this.getLayout();
    if (x >= layout.rightScaleLeft && y >= layout.plotTop && y <= layout.plotBottom) {
      this.manualPriceRange = null;
      this.render();
      event.preventDefault();
    }
  }

  onPointerLeave() {
    this.crosshair = null;
    this.emitCrosshair(null);
    this.render();
  }

  emitCrosshair(index: number | null) {
    if (index === null || index === undefined) {
      this.crosshairCallbacks.forEach((callback) => callback({}));
      return;
    }
    const payload = {
      time: null,
      seriesData: new Map(),
    };
    this.series.forEach((series) => {
      const item = series.data[index];
      if (!item) {
        return;
      }
      payload.time = (payload.time || item.time) || null;
      payload.seriesData.set(series, item);
    });
    this.crosshairCallbacks.forEach((callback) => callback(payload));
  }

  getLayout() {
    const leftScaleWidth = DEFAULT_LEFT_SCALE_WIDTH;
    const rightScaleWidth = DEFAULT_RIGHT_SCALE_WIDTH;
    const timeScaleHeight = DEFAULT_TIME_SCALE_HEIGHT;
    return {
      leftScaleWidth,
      plotLeft: DEFAULT_PADDING + leftScaleWidth,
      plotTop: DEFAULT_PADDING,
      plotRight: this.width - DEFAULT_PADDING - rightScaleWidth,
      plotBottom: this.height - DEFAULT_PADDING - timeScaleHeight,
      rightScaleLeft: this.width - rightScaleWidth,
      rightScaleWidth,
      timeScaleTop: this.height - timeScaleHeight,
      timeScaleHeight,
    };
  }

  getPriceSeries() {
    return this.series.find(
      (series) => series.type === CandlestickSeries || series.type === BarSeries || series.type === LineSeries,
    ) || null;
  }

  getVolumeSeries() {
    return this.series.find((series) => series.type === HistogramSeries) || null;
  }

  getNearestIndex(x: number, count: number, layout: any) {
    if (count <= 1) {
      return 0;
    }
    const visibleRange = this.getVisibleRange(count);
    const span = Math.max(visibleRange.to - visibleRange.from, 1);
    const ratio = (x - layout.plotLeft) / Math.max(layout.plotRight - layout.plotLeft, 1);
    const logicalIndex = visibleRange.from + span * ratio;
    return clamp(Math.round(logicalIndex), 0, count - 1);
  }

  getX(index: number, count: number, layout: any) {
    if (count <= 1) {
      return layout.plotLeft + (layout.plotRight - layout.plotLeft) / 2;
    }
    const visibleRange = this.getVisibleRange(count);
    const span = Math.max(visibleRange.to - visibleRange.from, 1);
    const ratio = (index - visibleRange.from) / span;
    return layout.plotLeft + (layout.plotRight - layout.plotLeft) * ratio;
  }

  getPaneRect(scaleMargins: any, layout: any) {
    const totalHeight = layout.plotBottom - layout.plotTop;
    const top = layout.plotTop + totalHeight * toNumber(scaleMargins.top, 0);
    const bottom = layout.plotBottom - totalHeight * toNumber(scaleMargins.bottom, 0);
    return {
      top,
      bottom,
      height: Math.max(1, bottom - top),
    };
  }

  getPriceRange() {
    if (this.manualPriceRange) {
      return this.manualPriceRange;
    }
    const priceSeries = this.getPriceSeries();
    if (!priceSeries || !priceSeries.data.length) {
      return { min: 0, max: 1 };
    }
    const visibleRange = this.getVisibleRange(priceSeries.data.length);
    const startIndex = Math.max(0, Math.floor(visibleRange.from));
    const endIndex = Math.min(priceSeries.data.length - 1, Math.ceil(visibleRange.to));
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    priceSeries.data.slice(startIndex, endIndex + 1).forEach((item) => {
      const low = item.low === undefined ? item.value : item.low;
      const high = item.high === undefined ? item.value : item.high;
      min = Math.min(min, toNumber(low, 0));
      max = Math.max(max, toNumber(high, 0));
    });
    if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
      const anchor = Number.isFinite(min) ? min : 0;
      return { min: anchor * 0.98, max: anchor * 1.02 + 1 };
    }
    const padding = (max - min) * 0.06;
    return { min: min - padding, max: max + padding };
  }

  zoomPriceRangeAtY(y: number, zoomFactor: number, layout: any) {
    const priceSeries = this.getPriceSeries();
    if (!priceSeries || !priceSeries.data.length) {
      return;
    }
    const priceRect = this.getPaneRect(priceSeries.scaleMargins, layout);
    const range = this.getPriceRange();
    const anchor = this.yToPrice(y, range, priceRect);
    const span = Math.max(range.max - range.min, 1e-9);
    const nextSpan = span * zoomFactor;
    const ratio = (anchor - range.min) / span;
    const nextMin = anchor - nextSpan * ratio;
    this.manualPriceRange = {
      min: nextMin,
      max: nextMin + nextSpan,
    };
    this.render();
  }

  getZoomSensitivity() {
    return clamp(toNumber(this.options.interaction?.zoomSensitivity, 0.55), 0.2, 1.5);
  }

  getWheelZoomFactor(deltaY: number) {
    const step = 0.18 * this.getZoomSensitivity();
    return deltaY > 0 ? 1 + step : 1 / (1 + step);
  }

  getVolumeRange() {
    const volumeSeries = this.getVolumeSeries();
    if (!volumeSeries || !volumeSeries.data.length) {
      return { min: 0, max: 1 };
    }
    const visibleRange = this.getVisibleRange(volumeSeries.data.length);
    const startIndex = Math.max(0, Math.floor(visibleRange.from));
    const endIndex = Math.min(volumeSeries.data.length - 1, Math.ceil(visibleRange.to));
    let max = 0;
    volumeSeries.data.slice(startIndex, endIndex + 1).forEach((item) => {
      max = Math.max(max, toNumber(item.value, 0));
    });
    return { min: 0, max: Math.max(max, 1) };
  }

  getVisibleRange(count: number) {
    if (count <= 1) {
      this.visibleRange = { from: 0, to: 0 };
      return this.visibleRange;
    }
    if (!this.visibleRange) {
      this.visibleRange = { from: 0, to: count - 1 };
    }
    this.visibleRange = this.clampVisibleRange(this.visibleRange.from, this.visibleRange.to, count);
    return this.visibleRange;
  }

  clampVisibleRange(from: number, to: number, count: number) {
    if (count <= 1) {
      return { from: 0, to: 0 };
    }
    const maxIndex = count - 1;
    let safeFrom = Number.isFinite(from) ? from : 0;
    let safeTo = Number.isFinite(to) ? to : maxIndex;
    let span = Math.max(safeTo - safeFrom, 1);
    span = Math.min(span, maxIndex);
    if (safeFrom < 0) {
      safeTo -= safeFrom;
      safeFrom = 0;
    }
    if (safeTo > maxIndex) {
      safeFrom -= safeTo - maxIndex;
      safeTo = maxIndex;
    }
    safeFrom = Math.max(0, safeFrom);
    safeTo = safeFrom + span;
    if (safeTo > maxIndex) {
      safeTo = maxIndex;
      safeFrom = Math.max(0, safeTo - span);
    }
    return { from: safeFrom, to: safeTo };
  }

  getVisibleIndexes(count: number) {
    const visibleRange = this.getVisibleRange(count);
    return {
      startIndex: Math.max(0, Math.floor(visibleRange.from) - 1),
      endIndex: Math.min(count - 1, Math.ceil(visibleRange.to) + 1),
    };
  }

  priceToY(value: number, range: { min: number; max: number }, rect: { bottom: number; height: number }) {
    const safeValue = toNumber(value, range.min);
    const normalized = (safeValue - range.min) / Math.max(range.max - range.min, 1e-9);
    return rect.bottom - normalized * rect.height;
  }

  yToPrice(y: number, range: { min: number; max: number }, rect: { bottom: number; height: number }) {
    const ratio = clamp((rect.bottom - y) / Math.max(rect.height, 1), 0, 1);
    return range.min + (range.max - range.min) * ratio;
  }

  render() {
    const ctx = this.ctx;
    const layout = this.getLayout();
    const priceSeries = this.getPriceSeries();
    const volumeSeries = this.getVolumeSeries();

    ctx.clearRect(0, 0, this.width, this.height);
    ctx.fillStyle = this.options.layout?.background?.color || "#ffffff";
    ctx.fillRect(0, 0, this.width, this.height);

    this.drawGrid(ctx, layout, priceSeries);
    this.drawVolumeSeries(ctx, layout, volumeSeries);
    this.drawPriceSeries(ctx, layout, priceSeries);
    this.drawMarkers(ctx, layout, priceSeries);
    this.drawAxes(ctx, layout, priceSeries);
    this.drawVolumeAxis(ctx, layout, volumeSeries);
    this.drawCrosshair(ctx, layout, priceSeries);
  }

  drawGrid(ctx: CanvasRenderingContext2D, layout: any, priceSeries: SeriesApi | null) {
    const priceRange = this.getPriceRange();
    const priceRect = this.getPaneRect(
      priceSeries?.scaleMargins || { top: 0.08, bottom: 0.28 },
      layout,
    );
    const verticalCount: number = DEFAULT_TIME_TICKS;
    const horizontalCount: number = DEFAULT_GRID_LINES;
    ctx.save();
    ctx.strokeStyle = this.options.grid?.horzLines?.color || "#e8e8e8";
    ctx.lineWidth = 1;

    for (let i = 0; i < horizontalCount; i += 1) {
      const ratio = horizontalCount === 1 ? 0 : i / (horizontalCount - 1);
      const y = priceRect.top + priceRect.height * ratio;
      ctx.beginPath();
      ctx.moveTo(layout.plotLeft, y);
      ctx.lineTo(layout.plotRight, y);
      ctx.stroke();
    }

    ctx.strokeStyle = this.options.grid?.vertLines?.color || "#efefef";
    for (let i = 0; i < verticalCount; i += 1) {
      const ratio = verticalCount === 1 ? 0 : i / (verticalCount - 1);
      const x = layout.plotLeft + (layout.plotRight - layout.plotLeft) * ratio;
      ctx.beginPath();
      ctx.moveTo(x, layout.plotTop);
      ctx.lineTo(x, layout.plotBottom);
      ctx.stroke();
    }

    ctx.fillStyle = this.options.layout?.textColor || "#6b7280";
    ctx.font = "12px 'IBM Plex Sans KR', sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i < horizontalCount; i += 1) {
      const ratio = horizontalCount === 1 ? 0 : i / (horizontalCount - 1);
      const y = priceRect.top + priceRect.height * ratio;
      const price = priceRange.max - (priceRange.max - priceRange.min) * ratio;
      ctx.fillText(Math.round(price).toLocaleString("ko-KR"), this.width - 8, y);
    }
    ctx.restore();
  }

  drawAxes(ctx: CanvasRenderingContext2D, layout: any, priceSeries: SeriesApi | null) {
    const data = priceSeries?.data || [];
    if (!data.length) {
      return;
    }
    ctx.save();
    ctx.fillStyle = this.options.layout?.textColor || "#6b7280";
    ctx.font = "12px 'IBM Plex Sans KR', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const visibleIndexes = this.getVisibleIndexes(data.length);
    const visibleCount = visibleIndexes.endIndex - visibleIndexes.startIndex + 1;
    const tickCount = Math.min(DEFAULT_TIME_TICKS, visibleCount);
    for (let i = 0; i < tickCount; i += 1) {
      const index = tickCount === 1
        ? visibleIndexes.startIndex
        : Math.round(
            visibleIndexes.startIndex
              + (i * (visibleIndexes.endIndex - visibleIndexes.startIndex)) / (tickCount - 1),
          );
      const x = this.getX(index, data.length, layout);
      const label = String(data[index].time || "").slice(5);
      ctx.fillText(label, x, layout.timeScaleTop + layout.timeScaleHeight / 2);
    }
    ctx.restore();
  }

  drawVolumeAxis(ctx: CanvasRenderingContext2D, layout: any, volumeSeries: SeriesApi | null) {
    if (!volumeSeries) {
      return;
    }
    const data = volumeSeries.data || [];
    if (!data.length) {
      return;
    }
    const volumeRect = this.getPaneRect(volumeSeries.scaleMargins, layout);
    const volumeRange = this.getVolumeRange();
    const tickCount: number = 2;

    ctx.save();
    ctx.strokeStyle = this.options.grid?.horzLines?.color || "#e8e8e8";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(layout.plotLeft, volumeRect.top);
    ctx.lineTo(layout.plotRight, volumeRect.top);
    ctx.stroke();

    ctx.fillStyle = this.options.layout?.textColor || "#6b7280";
    ctx.font = "12px 'IBM Plex Sans KR', sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i < tickCount; i += 1) {
      const ratio = tickCount === 1 ? 0 : i / (tickCount - 1);
      const y = volumeRect.top + volumeRect.height * ratio;
      const volume = volumeRange.max - (volumeRange.max - volumeRange.min) * ratio;
      ctx.fillText(Math.round(volume).toLocaleString("ko-KR"), layout.plotLeft - 8, y);
    }
    ctx.restore();
  }

  drawPriceSeries(ctx: CanvasRenderingContext2D, layout: any, priceSeries: SeriesApi | null) {
    if (!priceSeries) return;
    const data = priceSeries.data || [];
    if (!data.length) {
      return;
    }
    const priceRect = this.getPaneRect(priceSeries.scaleMargins, layout);
    const priceRange = this.getPriceRange();
    const visibleRange = this.getVisibleRange(data.length);
    const visibleCount = Math.max(visibleRange.to - visibleRange.from + 1, 1);
    const step = (layout.plotRight - layout.plotLeft) / visibleCount;
    const barHalfWidth = clamp(step * 0.22, 3, 8);
    const visibleIndexes = this.getVisibleIndexes(data.length);

    if (priceSeries.type === LineSeries) {
      this.drawLineSeries(ctx, layout, priceSeries);
      return;
    }

    ctx.save();
    ctx.beginPath();
    ctx.rect(layout.plotLeft, priceRect.top, layout.plotRight - layout.plotLeft, priceRect.height);
    ctx.clip();
    data.slice(visibleIndexes.startIndex, visibleIndexes.endIndex + 1).forEach((item, offset) => {
      const index = visibleIndexes.startIndex + offset;
      const x = this.getX(index, data.length, layout);
      const openY = this.priceToY(item.open, priceRange, priceRect);
      const highY = this.priceToY(item.high, priceRange, priceRect);
      const lowY = this.priceToY(item.low, priceRange, priceRect);
      const closeY = this.priceToY(item.close, priceRange, priceRect);
      const isUp = item.close >= item.open;
      const stroke = isUp
        ? (priceSeries.options.upColor || "#22ab94")
        : (priceSeries.options.downColor || "#f23645");

      if (priceSeries.type === CandlestickSeries) {
        const bodyWidth = clamp(step * 0.62, 4, 16);
        const bodyLeft = x - bodyWidth / 2;
        const bodyTop = Math.min(openY, closeY);
        const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
        ctx.lineWidth = 1.25;
        ctx.strokeStyle = isUp
          ? (priceSeries.options.wickUpColor || stroke)
          : (priceSeries.options.wickDownColor || stroke);
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();

        ctx.fillStyle = stroke;
        ctx.strokeStyle = isUp
          ? (priceSeries.options.borderUpColor || stroke)
          : (priceSeries.options.borderDownColor || stroke);
        ctx.fillRect(bodyLeft, bodyTop, bodyWidth, bodyHeight);
        ctx.strokeRect(bodyLeft, bodyTop, bodyWidth, bodyHeight);
        return;
      }

      ctx.lineWidth = 1.5;
      ctx.strokeStyle = stroke;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.moveTo(x - barHalfWidth, openY);
      ctx.lineTo(x, openY);
      ctx.moveTo(x, closeY);
      ctx.lineTo(x + barHalfWidth, closeY);
      ctx.stroke();
    });
    ctx.restore();
  }

  drawLineSeries(ctx: CanvasRenderingContext2D, layout: any, priceSeries: SeriesApi) {
    const data = priceSeries.data || [];
    if (!data.length) {
      return;
    }
    const priceRect = this.getPaneRect(priceSeries.scaleMargins, layout);
    const priceRange = this.getPriceRange();
    const visibleIndexes = this.getVisibleIndexes(data.length);

    ctx.save();
    ctx.beginPath();
    ctx.rect(layout.plotLeft, priceRect.top, layout.plotRight - layout.plotLeft, priceRect.height);
    ctx.clip();
    ctx.lineWidth = toNumber(priceSeries.options.lineWidth, 2);
    ctx.strokeStyle = priceSeries.options.color || "#2563eb";
    ctx.beginPath();
    data.slice(visibleIndexes.startIndex, visibleIndexes.endIndex + 1).forEach((item, offset) => {
      const index = visibleIndexes.startIndex + offset;
      const x = this.getX(index, data.length, layout);
      const y = this.priceToY(item.value, priceRange, priceRect);
      if (offset === 0) {
        ctx.moveTo(x, y);
        return;
      }
      ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.restore();
  }

  drawVolumeSeries(ctx: CanvasRenderingContext2D, layout: any, volumeSeries: SeriesApi | null) {
    if (!volumeSeries) return;
    const data = volumeSeries.data || [];
    if (!data.length) {
      return;
    }
    const volumeRect = this.getPaneRect(volumeSeries.scaleMargins, layout);
    const volumeRange = this.getVolumeRange();
    const visibleRange = this.getVisibleRange(data.length);
    const visibleCount = Math.max(visibleRange.to - visibleRange.from + 1, 1);
    const step = (layout.plotRight - layout.plotLeft) / visibleCount;
    const barWidth = Math.max(2, step * 0.7);
    const visibleIndexes = this.getVisibleIndexes(data.length);

    ctx.save();
    data.slice(visibleIndexes.startIndex, visibleIndexes.endIndex + 1).forEach((item, offset) => {
      const index = visibleIndexes.startIndex + offset;
      const x = this.getX(index, data.length, layout);
      const height = (toNumber(item.value, 0) / Math.max(volumeRange.max, 1)) * volumeRect.height;
      const top = volumeRect.bottom - height;
      ctx.fillStyle = item.color || alphaColor("#94a3b8", "66");
      ctx.fillRect(x - barWidth / 2, top, barWidth, height);
    });
    ctx.restore();
  }

  drawMarkers(ctx: CanvasRenderingContext2D, layout: any, priceSeries: SeriesApi | null) {
    if (!priceSeries) return;
    const markers = priceSeries.markers || [];
    const data = priceSeries.data || [];
    if (!markers.length || !data.length) {
      return;
    }
    const markersByTime = new Map<string, any[]>();
    markers.forEach((marker) => {
      const key = String(marker.time || "");
      const current = markersByTime.get(key) || [];
      current.push(marker);
      markersByTime.set(key, current);
    });
    const priceRect = this.getPaneRect(priceSeries.scaleMargins, layout);
    const priceRange = this.getPriceRange();
    const visibleIndexes = this.getVisibleIndexes(data.length);

    ctx.save();
    ctx.beginPath();
    ctx.rect(layout.plotLeft, priceRect.top, layout.plotRight - layout.plotLeft, priceRect.height);
    ctx.clip();
    ctx.font = "11px 'IBM Plex Sans KR', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    data.slice(visibleIndexes.startIndex, visibleIndexes.endIndex + 1).forEach((item, offset) => {
      const index = visibleIndexes.startIndex + offset;
      const itemMarkers = markersByTime.get(String(item.time || ""));
      if (!itemMarkers?.length) {
        return;
      }
      const x = this.getX(index, data.length, layout);
      const highY = this.priceToY(item.high, priceRange, priceRect);
      const lowY = this.priceToY(item.low, priceRange, priceRect);
      const midY = this.priceToY((toNumber(item.high) + toNumber(item.low)) / 2, priceRange, priceRect);
      itemMarkers.forEach((marker, markerIndex) => {
        let y = midY;
        if (marker.position === "aboveBar") {
          y = highY - 12 - markerIndex * 16;
        } else if (marker.position === "belowBar") {
          y = lowY + 12 + markerIndex * 16;
        }
        y = clamp(y, priceRect.top + 6, priceRect.bottom - 6);

        ctx.fillStyle = marker.color || "#94a3b8";
        ctx.strokeStyle = marker.color || "#94a3b8";
        if (marker.shape === "circle") {
          ctx.beginPath();
          ctx.arc(x, y, 4, 0, Math.PI * 2);
          ctx.fill();
        } else if (marker.shape === "square") {
          ctx.fillRect(x - 4, y - 4, 8, 8);
        } else {
          ctx.beginPath();
          ctx.moveTo(x, y - 5);
          ctx.lineTo(x - 5, y + 4);
          ctx.lineTo(x + 5, y + 4);
          ctx.closePath();
          ctx.fill();
        }

        if (marker.text) {
          ctx.fillStyle = marker.color || "#94a3b8";
          ctx.fillText(String(marker.text), x, y - 12);
        }
      });
    });

    ctx.restore();
  }

  drawCrosshair(ctx: CanvasRenderingContext2D, layout: any, priceSeries: SeriesApi | null) {
    if (!priceSeries) return;
    if (!this.crosshair || !priceSeries.data?.length) {
      return;
    }
    const data = priceSeries.data;
    const index = clamp(this.crosshair.index, 0, data.length - 1);
    const x = this.getX(index, data.length, layout);
    const priceRect = this.getPaneRect(priceSeries.scaleMargins, layout);
    const y = clamp(this.crosshair.y, priceRect.top, priceRect.bottom);
    const priceRange = this.getPriceRange();
    const label = data[index]?.time || "";
    const priceLabel = this.yToPrice(y, priceRange, priceRect);

    ctx.save();
    ctx.strokeStyle = "#94a3b8";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x, layout.plotTop);
    ctx.lineTo(x, layout.plotBottom);
    ctx.moveTo(layout.plotLeft, y);
    ctx.lineTo(layout.plotRight, y);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.font = "12px 'IBM Plex Sans KR', sans-serif";
    ctx.textBaseline = "middle";

    const priceText = Math.round(priceLabel).toLocaleString("ko-KR");
    const priceBoxWidth = ctx.measureText(priceText).width + 14;
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(this.width - priceBoxWidth - 6, y - 10, priceBoxWidth, 20);
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.fillText(priceText, this.width - priceBoxWidth / 2 - 6, y);

    const timeText = String(label);
    const timeBoxWidth = ctx.measureText(timeText).width + 14;
    const timeX = clamp(x - timeBoxWidth / 2, 6, this.width - timeBoxWidth - 6);
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(timeX, layout.timeScaleTop + 4, timeBoxWidth, 20);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(timeText, timeX + timeBoxWidth / 2, layout.timeScaleTop + 14);
    ctx.restore();
  }
}

export function createChart(container: HTMLElement, options: any = {}) {
  return new ChartApi(container, options);
}

export function createSeriesMarkers(series: SeriesApi, markers: any[]) {
  return new MarkerHandle(series, markers);
}
