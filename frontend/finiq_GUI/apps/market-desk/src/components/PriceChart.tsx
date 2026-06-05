"use client"

import { useEffect, useRef } from "react";
import { 
  createChart, 
  CandlestickSeries, 
  HistogramSeries, 
  createSeriesMarkers,
  ChartApi
} from "@/lib/charts";

interface PriceChartProps {
  data: any[];
  markers: any[];
  title: string;
  subtitle: string;
  onCrosshairMove?: (candle: any) => void;
}

export function PriceChart({ data, markers, title, subtitle, onCrosshairMove }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ChartApi | null>(null);
  const candleSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);

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
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22ab94",
      downColor: "#f23645",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.76,
        bottom: 0,
      },
    });

    chart.subscribeCrosshairMove((param: any) => {
      if (!param || !param.time) {
        if (onCrosshairMove) onCrosshairMove(null);
        return;
      }
      const candle = param.seriesData.get(candleSeries);
      const volume = param.seriesData.get(volumeSeries);
      if (onCrosshairMove) {
        onCrosshairMove({
          time: param.time,
          open: candle?.open,
          high: candle?.high,
          low: candle?.low,
          close: candle?.close,
          volume: volume?.value,
        });
      }
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry && chartRef.current) {
        chartRef.current.applyOptions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
        chartRef.current.timeScale().fitContent();
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.destroy();
      }
    };
  }, []); // Only on mount

  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || !volumeSeriesRef.current) return;

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
      color: d.color + "66",
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    createSeriesMarkers(candleSeriesRef.current, markers);
    chartRef.current.timeScale().fitContent();
  }, [data, markers]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-col mb-4">
        <h3 className="text-lg font-bold text-slate-900">{title}</h3>
        <p className="text-sm text-slate-500">{subtitle}</p>
      </div>
      <div ref={containerRef} className="flex-1 min-h-[400px] w-full" />
    </div>
  );
}
