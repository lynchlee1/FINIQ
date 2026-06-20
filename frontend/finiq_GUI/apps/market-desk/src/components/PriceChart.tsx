"use client";

import { useEffect, useRef } from "react";
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
  text?: string;
};

interface PriceChartProps {
  data: PriceChartDatum[];
  markers: PriceChartMarker[];
  title: string;
  subtitle: string;
  chartType?: "candlestick" | "line";
  showHeader?: boolean;
  zoomSensitivity?: number;
  markerPlacement?: MarkerPlacementOverride;
  markerShape?: MarkerShapeOverride;
  onCrosshairMove?: (candle: any) => void;
}

function volumeColor(datum: PriceChartDatum) {
  if (datum.color) {
    return datum.color.endsWith("66") ? datum.color : `${datum.color}66`;
  }
  return datum.close >= datum.open ? "rgba(34, 171, 148, 0.38)" : "rgba(242, 54, 69, 0.38)";
}

export function PriceChart({
  data,
  markers,
  title,
  subtitle,
  chartType = "candlestick",
  showHeader = true,
  zoomSensitivity = 0.55,
  markerPlacement = "default",
  markerShape = "default",
  onCrosshairMove,
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ChartApi | null>(null);
  const priceSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const hasFittedContentRef = useRef(false);
  const onCrosshairMoveRef = useRef(onCrosshairMove);

  useEffect(() => {
    onCrosshairMoveRef.current = onCrosshairMove;
  }, [onCrosshairMove]);

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
        onCrosshairMoveRef.current?.(null);
        return;
      }
      const candle = param.seriesData.get(priceSeries);
      const volume = param.seriesData.get(volumeSeries);
      onCrosshairMoveRef.current?.({
        time: param.time,
        open: candle?.open ?? candle?.value,
        high: candle?.high ?? candle?.value,
        low: candle?.low ?? candle?.value,
        close: candle?.close ?? candle?.value,
        volume: volume?.value,
      });
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
    const chartMarkers = markers.map((marker) => ({
      ...marker,
      position: markerPlacement === "default" ? marker.position : markerPlacement,
      shape: markerShape === "default" ? marker.shape : markerShape,
    }));
    createSeriesMarkers(priceSeriesRef.current, chartMarkers);
    if (!hasFittedContentRef.current) {
      chartRef.current.timeScale().fitContent();
      hasFittedContentRef.current = true;
    }
  }, [chartType, data, markerPlacement, markerShape, markers]);

  return (
    <div className="flex h-full flex-col">
      {showHeader ? (
        <div className="mb-4 flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{title}</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
        </div>
      ) : null}
      <div ref={containerRef} className="min-h-[400px] w-full flex-1" />
    </div>
  );
}
