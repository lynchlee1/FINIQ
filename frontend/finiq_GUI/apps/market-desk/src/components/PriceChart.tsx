"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LogicalRange,
  type MouseEventParams,
  type SeriesMarker,
  type SeriesMarkerBarPosition,
  type Time,
} from "lightweight-charts";

type PriceChartDatum = {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  color?: string;
};

type PriceChartMarker = {
  time: Time;
  position?: "aboveBar" | "belowBar" | "inBar";
  shape?: "circle" | "square" | "arrowUp" | "arrowDown";
  color?: string;
  text?: string;
};

interface PriceChartProps {
  data: PriceChartDatum[];
  markers: PriceChartMarker[];
  title: string;
  subtitle: string;
  onCrosshairMove?: (candle: any) => void;
}

function markerShape(shape: PriceChartMarker["shape"]): SeriesMarker<Time>["shape"] {
  if (shape === "square" || shape === "arrowUp" || shape === "arrowDown") {
    return shape;
  }
  return "circle";
}

function markerPosition(position: PriceChartMarker["position"]): SeriesMarkerBarPosition {
  if (position === "belowBar" || position === "inBar") {
    return position;
  }
  return "aboveBar";
}

function markerColor(color: string | undefined) {
  return color || "#64748b";
}

function volumeColor(datum: PriceChartDatum) {
  if (datum.color) {
    return datum.color.endsWith("66") ? datum.color : `${datum.color}66`;
  }
  return datum.close >= datum.open ? "rgba(34, 171, 148, 0.38)" : "rgba(242, 54, 69, 0.38)";
}

export function PriceChart({ data, markers, title, subtitle, onCrosshairMove }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markerApiRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const hasUserViewportRef = useRef(false);
  const suppressViewportTrackingRef = useRef(false);
  const onCrosshairMoveRef = useRef(onCrosshairMove);

  useEffect(() => {
    onCrosshairMoveRef.current = onCrosshairMove;
  }, [onCrosshairMove]);

  const candleData = useMemo<CandlestickData<Time>[]>(
    () =>
      data.map((d) => ({
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      })),
    [data],
  );

  const volumeData = useMemo<HistogramData<Time>[]>(
    () =>
      data.map((d) => ({
        time: d.time,
        value: d.volume ?? 0,
        color: volumeColor(d),
      })),
    [data],
  );

  const seriesMarkers = useMemo<SeriesMarker<Time>[]>(
    () =>
      markers.map((marker) => ({
        time: marker.time,
        position: markerPosition(marker.position),
        shape: markerShape(marker.shape),
        color: markerColor(marker.color),
        text: marker.text,
      })),
    [markers],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: Math.max(400, container.clientHeight),
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#5f6f83",
        fontFamily: "'IBM Plex Sans KR', Inter, sans-serif",
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.18)" },
        horzLines: { color: "rgba(148, 163, 184, 0.18)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: {
          top: 0.08,
          bottom: 0.28,
        },
      },
      timeScale: {
        borderVisible: false,
        rightOffset: 6,
        barSpacing: 10,
        fixLeftEdge: false,
        fixRightEdge: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: true,
        axisDoubleClickReset: true,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22ab94",
      downColor: "#f23645",
      wickUpColor: "#22ab94",
      wickDownColor: "#f23645",
      borderVisible: false,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.76,
        bottom: 0,
      },
    });

    const markerApi = createSeriesMarkers(candleSeries, []);

    const onVisibleRangeChange = (_range: LogicalRange | null) => {
      if (!suppressViewportTrackingRef.current) {
        hasUserViewportRef.current = true;
      }
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onVisibleRangeChange);

    chart.subscribeCrosshairMove((param: MouseEventParams<Time>) => {
      if (!param || !param.time) {
        onCrosshairMoveRef.current?.(null);
        return;
      }
      const candle = param.seriesData.get(candleSeries) as CandlestickData<Time> | undefined;
      const volume = param.seriesData.get(volumeSeries) as HistogramData<Time> | undefined;
      onCrosshairMoveRef.current?.({
        time: param.time,
        open: candle?.open,
        high: candle?.high,
        low: candle?.low,
        close: candle?.close,
        volume: volume?.value,
      });
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    markerApiRef.current = markerApi;

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry || !chartRef.current) return;
      chartRef.current.applyOptions({
        width: Math.max(1, Math.round(entry.contentRect.width)),
        height: Math.max(400, Math.round(entry.contentRect.height)),
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onVisibleRangeChange);
      markerApi.detach();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      markerApiRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const markerApi = markerApiRef.current;
    if (!chart || !candleSeries || !volumeSeries || !markerApi) return;

    const visibleRange = chart.timeScale().getVisibleLogicalRange();
    candleSeries.setData(candleData);
    volumeSeries.setData(volumeData);
    markerApi.setMarkers(seriesMarkers);

    suppressViewportTrackingRef.current = true;
    if (hasUserViewportRef.current && visibleRange) {
      chart.timeScale().setVisibleLogicalRange(visibleRange);
    } else {
      chart.timeScale().fitContent();
    }
    suppressViewportTrackingRef.current = false;
  }, [candleData, seriesMarkers, volumeData]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex flex-col">
        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{title}</h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
      </div>
      <div ref={containerRef} className="min-h-[400px] w-full flex-1" />
    </div>
  );
}
