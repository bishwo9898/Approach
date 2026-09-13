"use client";

import * as echarts from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { formatDate, formatMeasurement } from "@/lib/format";
import type { MetricDefinition, MetricSeriesPoint } from "@/lib/types";

// Registered explicitly rather than importing all of ECharts: this is the only
// chart type Phase 1 needs and the bundle should say so.
echarts.use([
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

/**
 * Session-by-session progression for one metric.
 *
 * Deliberate choices that keep the chart honest:
 *   - The y-axis is NOT forced to zero, because a velocity axis starting at 0
 *     flattens every real change out of visibility. It is also not zoomed to
 *     the data range alone, which would exaggerate noise; the axis is padded.
 *   - Preliminary sessions are drawn hollow so a provisional point is never
 *     mistaken for a confirmed one.
 *   - The tooltip always states the unit and the sample size behind the value.
 */
export function ProgressionChart({
  definition,
  points,
  recordValue,
  height = 260,
}: {
  definition: MetricDefinition;
  points: MetricSeriesPoint[];
  recordValue?: number | null;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current || points.length === 0) return;

    const chart = echarts.init(containerRef.current, undefined, {
      renderer: "canvas",
    });
    chartRef.current = chart;

    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const pad = Math.max((max - min) * 0.25, max * 0.01, 0.5);

    chart.setOption({
      animation: false,
      grid: { top: 16, right: 16, bottom: 28, left: 48 },
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const items = params as Array<{ dataIndex: number }>;
          const point = points[items[0]?.dataIndex ?? 0];
          if (!point) return "";
          const status = point.source_status === "VERIFIED" ? "Verified" : "Preliminary";
          return [
            `<strong>${formatDate(point.observed_on)}</strong>`,
            formatMeasurement(point.value, definition.unit, definition.display_precision),
            `n=${point.sample_size} · ${status}`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: points.map((p) => formatDate(p.observed_on)),
        axisLabel: { fontSize: 10, color: "#64748b" },
        axisLine: { lineStyle: { color: "#e2e8f0" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        min: Number((min - pad).toFixed(2)),
        max: Number((max + pad).toFixed(2)),
        axisLabel: {
          fontSize: 10,
          color: "#64748b",
          formatter: (value: number) => value.toFixed(definition.display_precision),
        },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
      },
      series: [
        {
          type: "line",
          data: values,
          smooth: false,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { width: 2, color: "#1e293b" },
          itemStyle: {
            color: (params: { dataIndex: number }) =>
              points[params.dataIndex]?.source_status === "VERIFIED"
                ? "#1e293b"
                : "#ffffff",
            borderColor: "#1e293b",
            borderWidth: 2,
          },
          markLine: recordValue
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { type: "dashed", color: "#16a34a", width: 1 },
                label: {
                  formatter: `PR ${recordValue.toFixed(definition.display_precision)}`,
                  fontSize: 10,
                  color: "#16a34a",
                  position: "insideEndTop",
                },
                data: [{ yAxis: recordValue }],
              }
            : undefined,
        },
      ],
    });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [points, definition, recordValue]);

  if (points.length === 0) {
    return (
      <EmptyState
        title="No sessions in this range"
        description="Widen the time range, or import a TrackMan session for this athlete."
      />
    );
  }

  return (
    <div className="space-y-2">
      <div
        ref={containerRef}
        style={{ height }}
        role="img"
        aria-label={`${definition.display_name} progression, ${points.length} sessions, in ${definition.unit}`}
      />
      <p className="text-[11px] text-muted-foreground">
        {definition.display_name} in {definition.unit} · {points.length} sessions · hollow
        points are preliminary TrackMan data
      </p>
    </div>
  );
}
