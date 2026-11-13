"use client";

import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type Fmt, formatValue } from "./fmt";

export type Series = { key: string; label: string; color: string; width?: number };

type Props = {
  data: Record<string, string | number | null>[];
  series: Series[];
  format: Fmt;
  xKey?: string;
  markers?: { n: number; date: string; at?: string }[];
  refY?: { y: number; label: string };
  height?: number;
  log?: boolean;
  ariaLabel: string;
};

const AXIS = { stroke: "var(--axis)", fontSize: 11, fill: "var(--muted)" };
const MAX_TICKS = 8;

/** One tick at the first point of each month, thinned to at most MAX_TICKS (no repeated labels).
 * A series that starts mid-month gets no tick at its first point: it would collide with the next. */
function monthTicks(xs: string[]): string[] {
  const firsts = xs.filter((x, i) => i > 0 && x.slice(0, 7) !== xs[i - 1].slice(0, 7));
  if (xs.length > 0 && (firsts.length === 0 || xs[0].length === 7 || xs[0].slice(8, 10) === "01")) {
    firsts.unshift(xs[0]);
  }
  const step = Math.ceil(firsts.length / MAX_TICKS);
  return firsts.filter((_, i) => i % step === 0);
}

export function TimeChart({
  data,
  series,
  format,
  xKey = "date",
  markers = [],
  refY,
  height = 260,
  log = false,
  ariaLabel,
}: Props) {
  return (
    <div role="img" aria-label={ariaLabel} className="w-full">
      <ResponsiveContainer width="100%" height={height} initialDimension={{ width: 640, height }}>
        <ComposedChart data={data} margin={{ top: 18, right: 28, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis
            dataKey={xKey}
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: "var(--axis)" }}
            ticks={monthTicks(data.map((d) => String(d[xKey])))}
            interval={0}
            tickFormatter={(d: string) => d.slice(0, 7)}
          />
          <YAxis
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={56}
            scale={log ? "log" : "auto"}
            domain={log ? ["auto", "auto"] : [0, "auto"]}
            allowDataOverflow={false}
            tickFormatter={(v: number) => formatValue(v, format, true)}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface)",
              border: "1px solid var(--ring)",
              borderRadius: 4,
              fontSize: 12,
              color: "var(--ink)",
            }}
            labelStyle={{ color: "var(--ink-2)" }}
            formatter={(v) => (typeof v === "number" ? formatValue(v, format) : String(v))}
          />
          {series.length > 1 && (
            <Legend
              wrapperStyle={{ fontSize: 12 }}
              iconType="plainline"
              formatter={(v) => <span style={{ color: "var(--ink-2)" }}>{v}</span>}
            />
          )}
          {refY && (
            <ReferenceLine
              y={refY.y}
              stroke="var(--ink-2)"
              strokeWidth={1}
              label={{ value: refY.label, position: "insideTopRight", fontSize: 11, fill: "var(--ink-2)" }}
            />
          )}
          {markers.map((m) => (
            <ReferenceLine
              key={m.n}
              x={m.at ?? m.date}
              stroke="var(--axis)"
              strokeWidth={1}
              label={{ value: String(m.n), position: "top", fontSize: 11, fill: "var(--ink)" }}
            />
          ))}
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={s.width ?? 2}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
