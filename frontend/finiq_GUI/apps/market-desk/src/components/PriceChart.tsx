"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
  type ChartApi,
} from "@/lib/charts";

type PriceChartDatum = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  color?: string;
};

type PriceChartMarkerPosition = "aboveBar" | "belowBar" | "inBar" | "paneTop" | "paneBottom";
type MarkerPlacementOverride = "default" | PriceChartMarkerPosition;
type MarkerShapeOverride = "default" | "circle" | "square" | "arrowUp" | "arrowDown";

type PriceChartMarker = {
  time: string;
  position?: PriceChartMarkerPosition;
  shape?: Exclude<MarkerShapeOverride, "default">;
  color?: string;
  group?: string;
  size?: number;
  lineWidth?: number;
  text?: string;
};

type MarkerStyleConfig = {
  position: MarkerPlacementOverride;
  shape: MarkerShapeOverride;
  color: string;
  size: number;
  lineWidth: number;
};

interface PriceChartProps {
  data: PriceChartDatum[];
  markers: PriceChartMarker[];
  title: string;
  subtitle: string;
  chartType?: "candlestick" | "line";
  showHeader?: boolean;
  zoomSensitivity?: number;
  markerStyleDefault?: MarkerStyleConfig;
  markerStylesByGroup?: Record<string, MarkerStyleConfig>;
  onCrosshairMove?: (candle: any) => void;
}

function volumeColor(datum: PriceChartDatum) {
  if (datum.color) {
    return datum.color.endsWith("66") ? datum.color : `${datum.color}66`;
  }
  return datum.close >= datum.open ? "rgba(34, 171, 148, 0.38)" : "rgba(242, 54, 69, 0.38)";
}

function formatPrice(value?: number) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  return Number(value).toLocaleString("ko-KR", {
    maximumFractionDigits: 2,
  });
}

function formatSignedChange(value?: number) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  const sign = Number(value) > 0 ? "+" : "";
  return `${sign}${formatPrice(value)}`;
}

function formatPercentChange(value?: number, previousClose?: number) {
  if (!Number.isFinite(value) || !Number.isFinite(previousClose) || Number(previousClose) === 0) {
    return "-";
  }
  const percent = (Number(value) / Math.abs(Number(previousClose))) * 100;
  const sign = percent > 0 ? "+" : "";
  return `${sign}${percent.toLocaleString("ko-KR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

function formatVolume(value?: number) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  const volume = Number(value);
  if (Math.abs(volume) >= 1_000_000) {
    return `${(volume / 1_000_000).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}M`;
  }
  if (Math.abs(volume) >= 1_000) {
    return `${(volume / 1_000).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}K`;
  }
  return volume.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
}

function resolveMarkerStyle(
  marker: PriceChartMarker,
  markerStyleDefault: MarkerStyleConfig,
  markerStylesByGroup: Record<string, MarkerStyleConfig>,
) {
  const groupStyle = marker.group ? markerStylesByGroup[marker.group] : undefined;
  return {
    ...marker,
    position: groupStyle?.position === "default" ? marker.position : groupStyle?.position ?? (markerStyleDefault.position === "default" ? marker.position : markerStyleDefault.position),
    shape: groupStyle?.shape === "default" ? marker.shape : groupStyle?.shape ?? (markerStyleDefault.shape === "default" ? marker.shape : markerStyleDefault.shape),
    color: groupStyle?.color ?? markerStyleDefault.color ?? marker.color,
    size: groupStyle?.size ?? markerStyleDefault.size,
    lineWidth: groupStyle?.lineWidth ?? markerStyleDefault.lineWidth,
  };
}

export function PriceChart({
  data,
  markers,
  title,
  subtitle,
  chartType = "candlestick",
  showHeader = true,
  zoomSensitivity = 0.55,
  markerStyleDefault = { position: "default", shape: "default", color: "#94a3b8", size: 4, lineWidth: 1 },
  markerStylesByGroup = {},
  onCrosshairMove,
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ChartApi | null>(null);
  const priceSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const hasFittedContentRef = useRef(false);
  const onCrosshairMoveRef = useRef(onCrosshairMove);
  const [activeCandle, setActiveCandle] = useState<PriceChartDatum | null>(null);

  useEffect(() => {
    onCrosshairMoveRef.current = onCrosshairMove;
  }, [onCrosshairMove]);

  useEffect(() => {
    setActiveCandle(null);
  }, [data]);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: "solid", color: "#ffffff" },
        textColor: "#5f6f83",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.18)" },
        horzLines: { color: "rgba(148, 163, 184, 0.18)" },
      },
      interaction: { zoomSensitivity },
    });

    const priceSeries =
      chartType === "line"
        ? chart.addSeries(LineSeries, {
            color: "#2563eb",
            lineWidth: 2,
          })
        : chart.addSeries(CandlestickSeries, {
            upColor: "#22ab94",
            downColor: "#f23645",
          });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
    });

    priceSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.04,
        bottom: 0.28,
      },
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.76,
        bottom: 0,
      },
    });

    chart.subscribeCrosshairMove((param: any) => {
      if (!param || !param.time) {
        setActiveCandle(null);
        onCrosshairMoveRef.current?.(null);
        return;
      }
      const candle = param.seriesData.get(priceSeries);
      const volume = param.seriesData.get(volumeSeries);
      const hoverCandle = {
        time: param.time,
        open: candle?.open ?? candle?.value,
        high: candle?.high ?? candle?.value,
        low: candle?.low ?? candle?.value,
        close: candle?.close ?? candle?.value,
        volume: volume?.value,
      };
      setActiveCandle(hoverCandle);
      onCrosshairMoveRef.current?.(hoverCandle);
    });

    chartRef.current = chart;
    priceSeriesRef.current = priceSeries;
    volumeSeriesRef.current = volumeSeries;
    hasFittedContentRef.current = false;

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry && chartRef.current) {
        chartRef.current.applyOptions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.destroy();
      }
      chartRef.current = null;
      priceSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [chartType]);

  useEffect(() => {
    chartRef.current?.applyOptions({
      interaction: { zoomSensitivity },
    });
  }, [zoomSensitivity]);

  useEffect(() => {
    if (!chartRef.current || !priceSeriesRef.current || !volumeSeriesRef.current) return;

    const candleData = data.map((d) => ({
      time: d.time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const volumeData = data.map((d) => ({
      time: d.time,
      value: d.volume,
      color: volumeColor(d),
    }));
    const lineData = data.map((d) => ({
      time: d.time,
      value: d.close,
      open: d.close,
      high: d.close,
      low: d.close,
      close: d.close,
    }));

    priceSeriesRef.current.setData(chartType === "line" ? lineData : candleData);
    volumeSeriesRef.current.setData(volumeData);
    const chartMarkers = markers.map((marker) => resolveMarkerStyle(marker, markerStyleDefault, markerStylesByGroup));
    createSeriesMarkers(priceSeriesRef.current, chartMarkers);
    if (!hasFittedContentRef.current) {
      chartRef.current.timeScale().fitContent();
      hasFittedContentRef.current = true;
    }
  }, [chartType, data, markerStyleDefault, markerStylesByGroup, markers]);

  const displayCandle = activeCandle ?? data[data.length - 1] ?? null;
  const displayIndex = displayCandle ? data.findIndex((datum) => datum.time === displayCandle.time) : -1;
  const previousClose = displayIndex > 0 ? data[displayIndex - 1].close : undefined;
  const priceChange = displayCandle && previousClose !== undefined ? displayCandle.close - previousClose : undefined;
  const changeIsNegative = Number(priceChange) < 0;

  return (
    <div className="flex h-full flex-col">
      {showHeader ? (
        <div className="mb-4 flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{title}</h3>
          {subtitle ? <p className="text-sm text-slate-500 dark:text-slate-400">{subtitle}</p> : null}
        </div>
      ) : null}
      <div className="relative min-h-[400px] w-full flex-1">
        {displayCandle ? (
          <div className="pointer-events-none absolute left-3 top-3 z-10 flex flex-wrap items-center gap-x-3 gap-y-1 rounded bg-white/85 px-2 py-1 text-xs font-medium text-slate-500 shadow-sm dark:bg-slate-950/80 dark:text-slate-300">
            <span>{displayCandle.time}</span>
            <span>O {formatPrice(displayCandle.open)}</span>
            <span>H {formatPrice(displayCandle.high)}</span>
            <span>L {formatPrice(displayCandle.low)}</span>
            <span>C {formatPrice(displayCandle.close)}</span>
            <span className={changeIsNegative ? "text-red-500" : "text-emerald-500"}>
              {formatSignedChange(priceChange)} ({formatPercentChange(priceChange, previousClose)})
            </span>
            <span>Vol {formatVolume(displayCandle.volume)}</span>
          </div>
        ) : null}
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </div>
  );
}
