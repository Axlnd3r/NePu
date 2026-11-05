import { AbsoluteFill, useVideoConfig } from "remotion";
import { theme } from "../theme";
import { GlassCard } from "./GlassCard";
import { LineChart, Point } from "./LineChart";
import { Narration } from "./Narration";

type Props = {
  text: string;
  highlight?: string[];
  series: Point[][];
  colors: string[];
  names: string[];
  /** Source file name shown in the provenance line. */
  source: string;
  formatValue: (v: number) => string;
  pulse?: number;
  yMax?: number;
  refLine?: { value: number; label: string };
  gap?: { upper: number; lower: number; label: string };
  refGap?: string;
  children?: React.ReactNode;
};

// Layout shared by the chart scenes: narration on top, a glass card with the chart, a provenance line.
// The background is transparent so the shared Backdrop shows through.
export const ChartScene: React.FC<Props> = ({ text, highlight, series, colors, names, source, formatValue, pulse = 0, yMax, refLine, gap, refGap, children }) => {
  const { width, height } = useVideoConfig();
  const pad = Math.round(width * 0.06);
  const cardPad = 28;
  const wide = width > height;
  const chartW = width - 2 * pad - 2 * cardPad;
  const chartH = Math.round(height * (wide ? 0.4 : 0.38));
  const first = series[0][0].date;
  const last = series[0].at(-1)!.date;

  return (
    <AbsoluteFill style={{ padding: pad, justifyContent: "center", gap: Math.round(height * 0.035) }}>
      <Narration text={text} highlight={highlight} maxWidth={wide ? "80%" : "92%"} />
      <GlassCard pulse={pulse} style={{ padding: cardPad, position: "relative" }}>
        <LineChart
          series={series} colors={colors} names={names} width={chartW} height={chartH}
          startFrame={24} pulse={pulse} yMax={yMax} refLine={refLine} gap={gap} refGap={refGap} formatValue={formatValue}
        />
        {children}
      </GlassCard>
      <div style={{ fontFamily: theme.font, fontSize: Math.round(width * theme.size.source), color: theme.muted, letterSpacing: "0.04em" }}>
        Source: {source} · {first} to {last}
      </div>
    </AbsoluteFill>
  );
};
